<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { errorMessage } from "@/api/client";
import SheetDiagram from "@/components/SheetDiagram.vue";
import SheetRunForm from "@/components/SheetRunForm.vue";
import { formatMoney } from "@/domain/orders";
import {
  formatDuration,
  groupPlacements,
  indexOrderItems,
  OUTCOME_LABELS,
  SHEET_STATUS_LABELS,
  SHEET_STATUSES,
  sheetStatusLabel,
  usedFraction,
} from "@/domain/production";
import type { Run } from "@/services/production";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";

const production = useProductionStore();
const catalog = useCatalogStore();
const orders = useOrdersStore();

const filter = ref("");
const planMaterial = ref<number | "">("");
const planning = ref(false);
const planError = ref("");
const planResult = ref("");
const running = ref<number | null>(null);
/** آخر تشغيل سُجّل في هذه الزيارة لكل لوح؛ الخادم لا يعرض سجل التشغيل بعد. */
const lastRun = ref<Record<number, Run>>({});

const percent = new Intl.NumberFormat("ar-u-nu-latn", { style: "percent", maximumFractionDigits: 0 });

const filters = computed(() => [
  { value: "", label: "الكل", count: production.sheets.length },
  ...SHEET_STATUSES.map((status) => ({
    value: status as string,
    label: SHEET_STATUS_LABELS[status],
    count: production.countByStatus[status] ?? 0,
  })),
]);

const items = computed(() => indexOrderItems(orders.orders));

/** الألواح جاهزة للعرض: اسم المادة، نسبة الاستعمال، ومفتاح الرسم بأسماء الطلبات. */
const cards = computed(() =>
  production.sheets
    .filter((sheet) => !filter.value || sheet.status === filter.value)
    .map((sheet) => {
      const material = catalog.materialById(sheet.material_id);
      return {
        sheet,
        material: material ? `${material.name} (${material.thickness_mm} مم)` : `مادة ${sheet.material_id}`,
        used: percent.format(usedFraction(sheet)),
        groups: groupPlacements(sheet).map((group) => {
          const item = items.value.get(group.orderItemId);
          return {
            ...group,
            orderId: item?.orderId,
            title: item
              ? `${catalog.templateBySlug(item.templateSlug)?.name ?? item.templateSlug} — ${item.customerName}`
              : `بند ${group.orderItemId}`,
          };
        }),
      };
    }),
);

onMounted(() => Promise.all([production.load(), catalog.ensureLoaded(), orders.ensureLoaded()]));

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
    if (planned.length > 0) filter.value = "";
  } catch (error) {
    planError.value = errorMessage(error);
  } finally {
    planning.value = false;
  }
}

function recorded(run: Run): void {
  lastRun.value[run.sheet_id] = run;
  running.value = null;
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
      @click="filter = option.value"
    >
      {{ option.label }} <span class="count">{{ option.count }}</span>
    </button>
  </div>

  <div v-if="production.loadError" class="notice" role="alert">
    {{ production.loadError }}
    <button type="button" class="btn retry" @click="production.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="production.loading && !production.loaded" class="muted" role="status">يحمّل الألواح…</p>
  <p v-else-if="production.sheets.length === 0" class="panel muted">
    لا ألواح بعد. أكِّد طلبًا ثم خطِّط ألواح مادته من الأعلى.
  </p>
  <p v-else-if="cards.length === 0" class="panel muted">لا ألواح بهذه الحالة.</p>

  <ul v-else class="cards">
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
          <RouterLink v-if="group.orderId" :to="{ name: 'order-detail', params: { id: group.orderId } }">
            طلب {{ group.orderId }}
          </RouterLink>
        </li>
      </ol>

      <div v-if="lastRun[card.sheet.id]" class="notice ok" role="status">
        سُجّل التشغيل: {{ OUTCOME_LABELS[lastRun[card.sheet.id].outcome] ?? lastRun[card.sheet.id].outcome }} ·
        {{ formatDuration(lastRun[card.sheet.id].duration_s) }} · كلفة المادة
        {{ formatMoney(lastRun[card.sheet.id].material_cost) }}
      </div>

      <SheetRunForm
        v-if="running === card.sheet.id"
        :sheet="card.sheet"
        @recorded="recorded"
        @cancel="running = null"
      />
      <div v-else-if="card.sheet.status === 'planned'" class="form-actions">
        <button type="button" class="btn" @click="running = card.sheet.id">تسجيل تشغيل</button>
      </div>
    </li>
  </ul>
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
.retry { margin-inline-start: 12px; }
</style>
