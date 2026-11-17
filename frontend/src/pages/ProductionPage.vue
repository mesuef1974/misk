<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { errorMessage } from "@/api/client";
import SheetDiagram from "@/components/SheetDiagram.vue";
import SheetRunForm from "@/components/SheetRunForm.vue";
import { formatInstant, formatMoney } from "@/domain/orders";
import {
  formatDuration,
  groupPlacements,
  OUTCOME_LABELS,
  SHEET_STATUS_LABELS,
  SHEET_STATUSES,
  sheetStatusLabel,
  usedFraction,
} from "@/domain/production";
import { useCatalogStore } from "@/stores/catalog";
import { useProductionStore } from "@/stores/production";

const production = useProductionStore();
const catalog = useCatalogStore();

const filter = ref("");
const planMaterial = ref<number | "">("");
const planning = ref(false);
const planError = ref("");
const planResult = ref("");
const running = ref<number | null>(null);
/** اللوح الذي ينتظر تأكيد إتلافه: الإتلاف لا رجعة فيه، فالضغطة الأولى تطلب التأكيد فقط. */
const confirmingScrap = ref<number | null>(null);
const scrapping = ref(false);
const scrapError = ref<Record<number, string>>({});

const percent = new Intl.NumberFormat("ar-u-nu-latn", { style: "percent", maximumFractionDigits: 0 });

// الأعداد والتصفية من الخادم: القائمة صفحات، وما حُمّل منها ليس الجدول كله.
const filters = computed(() => [
  { value: "", label: "الكل", count: production.totalAll },
  ...SHEET_STATUSES.map((status) => ({
    value: status as string,
    label: SHEET_STATUS_LABELS[status],
    count: production.countByStatus[status] ?? 0,
  })),
]);

/** الألواح جاهزة للعرض: اسم المادة، نسبة الاستعمال، مفتاح الرسم بأسماء الطلبات، وسجل التشغيل. */
const cards = computed(() =>
  production.sheets.map((sheet) => {
    const material = catalog.materialById(sheet.material_id);
    return {
      sheet,
      material: material ? `${material.name} (${material.thickness_mm} مم)` : `مادة ${sheet.material_id}`,
      used: percent.format(usedFraction(sheet)),
      groups: groupPlacements(sheet).map((group) => ({
        ...group,
        title: `${catalog.templateBySlug(group.templateSlug)?.name ?? group.templateSlug} — ${group.customerName}`,
      })),
      runs: sheet.runs.map((run) => ({
        id: run.id,
        outcome: run.outcome,
        summary: [
          OUTCOME_LABELS[run.outcome] ?? run.outcome,
          formatDuration(run.duration_s),
          `كلفة المادة ${formatMoney(run.material_cost)}`,
          formatInstant(run.created_at),
        ].join(" · "),
        notes: run.notes,
      })),
    };
  }),
);

function choose(value: string): Promise<void> {
  filter.value = value;
  return production.load(value);
}

onMounted(() => Promise.all([production.load(), catalog.ensureLoaded()]));

async function plan(): Promise<void> {
  if (planMaterial.value === "") return;
  planError.value = "";
  planResult.value = "";
  planning.value = true;
  try {
    const planned = await production.plan(planMaterial.value);
    const pieces = planned.reduce((sum, sheet) => sum + sheet.placements.length, 0);
    planResult.value =
      planned.length === 0
        ? "لا قطع تنتظر التخطيط لهذه المادة. تُخطَّط بنود الطلبات المؤكَّدة وقيد التنفيذ فقط."
        : `خُطِّطت ${pieces} قطعة على ${planned.length} لوح.`;
    // الألواح الجديدة مخطَّطة: تصفية بحالة أخرى تخفيها، فنعود إلى الكل.
    if (planned.length > 0 && filter.value !== "" && filter.value !== "planned") await choose("");
  } catch (error) {
    planError.value = errorMessage(error);
  } finally {
    planning.value = false;
  }
}

function recorded(): void {
  running.value = null;
}

async function scrap(sheetId: number): Promise<void> {
  if (confirmingScrap.value !== sheetId) {
    confirmingScrap.value = sheetId;
    return;
  }
  confirmingScrap.value = null;
  delete scrapError.value[sheetId];
  scrapping.value = true;
  try {
    await production.scrap(sheetId);
  } catch (error) {
    scrapError.value[sheetId] = errorMessage(error);
  } finally {
    scrapping.value = false;
  }
}
</script>

<template>
  <div class="page-head">
    <h1>الإنتاج</h1>
  </div>

  <form class="panel plan" @submit.prevent="plan">
    <label class="field">
      <span>تخطيط ألواح جديدة لمادة</span>
      <select v-model="planMaterial">
        <option value="">اختر المادة</option>
        <option v-for="material in catalog.materials" :key="material.id" :value="material.id">
          {{ material.name }} ({{ material.thickness_mm }} مم)
        </option>
      </select>
    </label>
    <button type="submit" class="btn primary" :disabled="planning || planMaterial === ''">
      {{ planning ? "يخطّط…" : "تخطيط الألواح" }}
    </button>
    <div v-if="planError" class="notice" role="alert">{{ planError }}</div>
    <div v-else-if="planResult" class="notice ok" role="status">{{ planResult }}</div>
  </form>

  <div class="filters" role="group" aria-label="تصفية بالحالة">
    <button
      v-for="option in filters"
      :key="option.value"
      type="button"
      class="chip"
      :class="{ active: filter === option.value }"
      :aria-pressed="filter === option.value"
      @click="choose(option.value)"
    >
      {{ option.label }} <span class="count">{{ option.count }}</span>
    </button>
  </div>

  <div v-if="production.loadError" class="notice" role="alert">
    {{ production.loadError }}
    <button type="button" class="btn retry" @click="production.load(filter)">إعادة المحاولة</button>
  </div>
  <p v-else-if="production.loading && !production.loaded" class="muted" role="status">يحمّل الألواح…</p>
  <p v-else-if="production.totalAll === 0" class="panel muted">
    لا ألواح بعد. أكِّد طلبًا ثم خطِّط ألواح مادته من الأعلى.
  </p>
  <p v-else-if="cards.length === 0" class="panel muted">لا ألواح بهذه الحالة.</p>

  <ul v-if="!production.loadError && cards.length > 0" class="cards" :aria-busy="production.loading">
    <li v-for="card in cards" :key="card.sheet.id" class="panel sheet-card">
      <div class="head">
        <strong>لوح {{ card.sheet.id }}</strong>
        <span class="muted">{{ card.material }}</span>
        <span class="state" :class="`is-${card.sheet.status}`">{{ sheetStatusLabel(card.sheet.status) }}</span>
        <span class="muted num used">
          {{ card.sheet.placements.length }} قطعة · مستعمل {{ card.used }}
        </span>
      </div>

      <SheetDiagram :sheet="card.sheet" />

      <ol class="legend">
        <li v-for="group in card.groups" :key="group.orderItemId">
          <span class="tag num">{{ group.number }}</span>
          <span>{{ group.title }}</span>
          <span class="muted num">× {{ group.copies }}</span>
          <RouterLink :to="{ name: 'order-detail', params: { id: group.orderId } }">
            طلب {{ group.orderId }}
          </RouterLink>
        </li>
      </ol>

      <section v-if="card.runs.length" class="runs" :aria-label="`سجل تشغيل اللوح ${card.sheet.id}`">
        <h3>سجل التشغيل</h3>
        <ol>
          <li v-for="run in card.runs" :key="run.id" :class="`is-${run.outcome}`">
            <span class="num">{{ run.summary }}</span>
            <span v-if="run.notes" class="muted">{{ run.notes }}</span>
          </li>
        </ol>
      </section>

      <div v-if="scrapError[card.sheet.id]" class="notice" role="alert">{{ scrapError[card.sheet.id] }}</div>

      <SheetRunForm
        v-if="running === card.sheet.id"
        :sheet="card.sheet"
        @recorded="recorded"
        @cancel="running = null"
      />
      <div v-else-if="card.sheet.status === 'planned'" class="form-actions">
        <button type="button" class="btn" @click="running = card.sheet.id">تسجيل تشغيل</button>
        <template v-if="confirmingScrap === card.sheet.id">
          <span class="muted">تُرفع قطع اللوح لتُخطَّط على لوح جديد، ولا رجعة.</span>
          <button type="button" class="btn danger" :disabled="scrapping" @click="scrap(card.sheet.id)">
            تأكيد الإتلاف
          </button>
          <button type="button" class="btn" @click="confirmingScrap = null">تراجع</button>
        </template>
        <button v-else type="button" class="btn" :disabled="scrapping" @click="scrap(card.sheet.id)">
          إتلاف اللوح
        </button>
      </div>
    </li>
  </ul>
  <div v-if="!production.loadError && production.hasMore" class="more">
    <span class="muted num">يعرض {{ production.sheets.length }} من {{ production.total }}</span>
    <button type="button" class="btn" :disabled="production.loadingMore" @click="production.loadMore()">
      {{ production.loadingMore ? "يحمّل…" : "تحميل المزيد" }}
    </button>
  </div>
</template>

<style scoped>
.plan { display: grid; grid-template-columns: minmax(220px, 1fr) auto; align-items: end; gap: 12px 16px; margin-block-end: 20px; }
.plan .notice { grid-column: 1 / -1; }
@media (max-width: 520px) { .plan { grid-template-columns: 1fr; } }
.head { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; margin-block-end: 12px; }
.used { margin-inline-start: auto; font-size: 15px; }
.state {
  padding-inline: 10px; border: 1px solid var(--line); border-radius: 999px;
  font-size: 14px; line-height: 1.9; white-space: nowrap; color: var(--muted); background: var(--bg);
}
.state.is-planned { border-color: var(--accent); color: var(--accent); }
.state.is-done { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.state.is-scrapped { border-color: var(--risk); color: var(--risk); }
.legend { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 4px; font-size: 15px; }
.legend li { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.tag {
  display: inline-flex; align-items: center; justify-content: center; min-inline-size: 26px; block-size: 26px;
  border: 1px solid var(--accent); border-radius: 6px; color: var(--accent); font-weight: 600;
}
.sheet-card .notice { margin-block-start: 12px; }
.runs { margin-block-start: 12px; }
.runs h3 { font-size: 15px; margin: 0 0 4px; color: var(--muted); font-weight: 600; }
.runs ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 15px; }
.runs li { display: flex; flex-wrap: wrap; gap: 2px 12px; padding-inline-start: 10px; border-inline-start: 3px solid var(--line); }
.runs li.is-ok { border-inline-start-color: var(--accent); }
.runs li.is-failed { border-inline-start-color: var(--risk); }
.retry { margin-inline-start: 12px; }
</style>
