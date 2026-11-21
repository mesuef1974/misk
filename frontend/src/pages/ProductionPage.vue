<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ApiError, errorMessage } from "@/api/client";
import LiveNotice from "@/components/LiveNotice.vue";
import SheetDiagram from "@/components/SheetDiagram.vue";
import SheetRunForm from "@/components/SheetRunForm.vue";
import { materialName, templateName } from "@/domain/catalog";
import { formatInstant, formatMoney } from "@/domain/orders";
import {
  formatDuration,
  groupPlacements,
  outcomeLabel,
  SHEET_STATUSES,
  sheetStatusLabel,
  usedFraction,
} from "@/domain/production";
import { currentLocale } from "@/i18n";
import type { Material } from "@/services/catalog";
import { useCatalogStore } from "@/stores/catalog";
import { PlanCancelled, useProductionStore } from "@/stores/production";

const production = useProductionStore();
const catalog = useCatalogStore();
const { t } = useI18n();

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

// الأرقام لاتينية في اللغتين؛ موضع علامة النسبة يتبع لغة الصفحة.
const percent = computed(
  () => new Intl.NumberFormat(currentLocale() === "ar" ? "ar-u-nu-latn" : "en", { style: "percent", maximumFractionDigits: 0 }),
);

const materialLabel = (material: Pick<Material, "name" | "name_en" | "thickness_mm">) =>
  t("production.material.named", { name: materialName(material), thickness: material.thickness_mm });

// الأعداد والتصفية من الخادم: القائمة صفحات، وما حُمّل منها ليس الجدول كله.
const filters = computed(() => [
  { value: "", label: t("production.filter.all"), count: production.totalAll },
  ...SHEET_STATUSES.map((status) => ({
    value: status as string,
    label: sheetStatusLabel(status),
    count: production.countByStatus[status] ?? 0,
  })),
]);

function templateLabel(slug: string): string {
  const template = catalog.templateBySlug(slug);
  return template ? templateName(template) : slug;
}

/** الألواح جاهزة للعرض: اسم المادة، نسبة الاستعمال، مفتاح الرسم بأسماء الطلبات، وسجل التشغيل. */
const cards = computed(() =>
  production.sheets.map((sheet) => {
    const material = catalog.materialById(sheet.material_id);
    return {
      sheet,
      material: material ? materialLabel(material) : t("production.material.unknown", { id: sheet.material_id }),
      used: percent.value.format(usedFraction(sheet)),
      groups: groupPlacements(sheet).map((group) => ({
        ...group,
        title: t("production.sheet.groupTitle", {
          template: templateLabel(group.templateSlug),
          customer: group.customerName,
        }),
      })),
      runs: sheet.runs.map((run) => ({
        id: run.id,
        outcome: run.outcome,
        summary: [
          outcomeLabel(run.outcome),
          formatDuration(run.duration_s),
          t("production.sheet.materialCost", { cost: formatMoney(run.material_cost) }),
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
// المهمة تمضي في الخادم؛ لا استطلاع لصفحة غادرها المستخدم.
onBeforeUnmount(() => production.stopPlanning());

async function plan(): Promise<void> {
  if (planMaterial.value === "") return;
  planError.value = "";
  planResult.value = "";
  planning.value = true;
  try {
    const { sheets: planned, waiting } = await production.plan(planMaterial.value);
    const pieces = planned.reduce((sum, sheet) => sum + sheet.placements.length, 0);
    // لا جديد لا يعني لا قطع: نقرة ثانية أو إعادة بعد المهلة تجد القطع على ألواح خُطِّطت قبلها.
    planResult.value =
      planned.length > 0
        ? t("production.plan.planned", { pieces, sheets: planned.length })
        : waiting > 0
          ? t("production.plan.alreadyPlanned", { waiting })
          : t("production.plan.nothing");
    // الألواح الجديدة مخطَّطة: تصفية بحالة أخرى تخفيها، فنعود إلى الكل.
    if (planned.length > 0 && filter.value !== "" && filter.value !== "planned") await choose("");
  } catch (error) {
    if (error instanceof PlanCancelled) return;
    planError.value = errorMessage(error);
    // انتهت المهلة والمهمة قد تكون ثبّتت ألواحها أو تثبّتها الآن: القائمة من الخادم لا من رد لم يصل.
    if (error instanceof ApiError && error.status === 504) await production.load(filter.value);
  } finally {
    planning.value = false;
  }
}

/** الزر الذي ضُغط يختفي مع تبدّل الأزرار؛ ينتقل التركيز إلى بديله كي لا يسقط إلى أول الصفحة. */
async function focusById(id: string): Promise<void> {
  await nextTick();
  document.getElementById(id)?.focus();
}

const sheetTitleId = (sheetId: number) => `sheet-${sheetId}-title`;

/** أين يذهب التركيز إن اختفى ما في البطاقة: الزر المفضَّل إن بقي، ثم عنوان البطاقة،
 *  فإن خرجت من التصفية فعنوان التالية ثم السابقة. الجيران من DOM كما رُسم الآن. */
function focusFallbacks(sheetId: number, preferred?: string): string[] {
  const titles = Array.from(document.querySelectorAll<HTMLElement>("[data-sheet-title]"), (element) => element.id);
  const index = titles.indexOf(sheetTitleId(sheetId));
  const neighbours = index === -1 ? [] : [titles[index + 1], titles[index - 1]].filter(Boolean);
  return [...(preferred ? [preferred] : []), sheetTitleId(sheetId), ...neighbours];
}

/** أول ما بقي من المرشّحين بعد الرسم، وإلا فعنوان الصفحة. */
async function focusFirst(ids: string[]): Promise<void> {
  await nextTick();
  for (const id of [...ids, "production-title"]) {
    const element = document.getElementById(id);
    if (element) {
      element.focus();
      return;
    }
  }
}

const sheetCard = (sheetId: number) => document.getElementById(sheetTitleId(sheetId))?.closest(".sheet-card") ?? null;

/** يُنقل التركيز فقط إن كان في البطاقة أو سقط إلى body باختفاء ما فيها.
 *  تركيز في مكان آخر (رقاقة تصفية أبدلت القائمة مثلًا) اختيار المستخدم فلا يُسرق. */
function focusBelongsTo(card: Element | null): boolean {
  const active = document.activeElement;
  return !active || active === document.body || (card?.contains(active) ?? false);
}

/** النموذج يُغلق: يعود التركيز إلى زر فتحه، أو إلى البطاقة إن أُغلق اللوح بتشغيل ناجح. */
function closeRunForm(sheetId: number): Promise<void> {
  const move = focusBelongsTo(sheetCard(sheetId));
  const targets = focusFallbacks(sheetId, `run-${sheetId}`);
  running.value = null;
  return move ? focusFirst(targets) : Promise.resolve();
}

// تشغيل ناجح يرفع اللوح من تصفية «مخطَّط» فيُزال النموذج معه، وVue لا يوصل `recorded` من مكوّن أُزيل.
// المراقب يجري قبل الرسم، فالبطاقة ما زالت في DOM ويُعرف جيرانها.
watch(
  () => running.value !== null && !production.sheets.some((sheet) => sheet.id === running.value),
  (gone) => {
    if (gone && running.value !== null) void closeRunForm(running.value);
  },
);

function cancelScrap(sheetId: number): Promise<void> {
  confirmingScrap.value = null;
  return focusById(`scrap-${sheetId}`);
}

async function scrap(sheetId: number): Promise<void> {
  if (confirmingScrap.value !== sheetId) {
    confirmingScrap.value = sheetId;
    // «تراجع» لا «تأكيد»: ضغطة Enter ثانية بالخطأ لا تُتلف اللوح.
    await focusById(`scrap-cancel-${sheetId}`);
    return;
  }
  // زرّا التأكيد يختفيان: عند الرفض يعود زر الإتلاف، وعند النجاح تبقى البطاقة بلا أزرار أو تخرج من التصفية.
  const targets = focusFallbacks(sheetId, `scrap-${sheetId}`);
  const card = sheetCard(sheetId);
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
  // أثناء الطلب قد ينقل المستخدم التركيز إلى غير البطاقة: لا يُعاد منه.
  if (focusBelongsTo(card)) await focusFirst(targets);
}
</script>

<template>
  <div class="page-head">
    <h1 id="production-title" tabindex="-1">{{ t("production.title") }}</h1>
  </div>

  <form class="panel plan" @submit.prevent="plan">
    <label class="field">
      <span>{{ t("production.plan.label") }}</span>
      <select v-model="planMaterial">
        <option value="">{{ t("production.plan.choose") }}</option>
        <option v-for="material in catalog.materials" :key="material.id" :value="material.id">
          {{ materialLabel(material) }}
        </option>
      </select>
    </label>
    <button type="submit" class="btn primary" :disabled="planning || planMaterial === ''">
      {{ planning ? t("production.plan.busy") : t("production.plan.submit") }}
    </button>
    <LiveNotice :message="planError" />
    <LiveNotice kind="status" :message="planError ? '' : planResult" />
  </form>

  <div class="filters" role="group" :aria-label="t('production.filter.label')">
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
    <button type="button" class="btn retry" @click="production.load(filter)">{{ t("production.list.retry") }}</button>
  </div>
  <p v-else-if="production.loading && !production.loaded" class="muted" role="status">{{ t("production.list.loading") }}</p>
  <div v-else-if="production.totalAll === 0" class="empty">
    <div class="inner"><div class="mark" aria-hidden="true"></div><p>{{ t("production.list.empty") }}</p></div>
  </div>
  <p v-else-if="cards.length === 0" class="panel muted">{{ t("production.list.noneInStatus") }}</p>

  <ul v-if="!production.loadError && cards.length > 0" class="cards" :aria-busy="production.loading">
    <li v-for="card in cards" :key="card.sheet.id" class="panel sheet-card">
      <div class="head">
        <strong :id="sheetTitleId(card.sheet.id)" data-sheet-title tabindex="-1">{{ t("production.sheet.title", { id: card.sheet.id }) }}</strong>
        <span class="muted">{{ card.material }}</span>
        <span class="state" :class="`is-${card.sheet.status}`">{{ sheetStatusLabel(card.sheet.status) }}</span>
        <span class="muted num used">
          {{ t("production.sheet.usage", { pieces: card.sheet.placements.length, used: card.used }) }}
        </span>
      </div>

      <SheetDiagram :sheet="card.sheet" />

      <ol class="legend">
        <li v-for="group in card.groups" :key="group.orderItemId">
          <span class="tag num">{{ group.number }}</span>
          <span>{{ group.title }}</span>
          <span class="muted num">× {{ group.copies }}</span>
          <RouterLink :to="{ name: 'order-detail', params: { id: group.orderId } }">
            {{ t("production.sheet.order", { id: group.orderId }) }}
          </RouterLink>
        </li>
      </ol>

      <section v-if="card.runs.length" class="runs" :aria-label="t('production.sheet.runsLabel', { id: card.sheet.id })">
        <h3>{{ t("production.sheet.runs") }}</h3>
        <ol>
          <li v-for="run in card.runs" :key="run.id" :class="`is-${run.outcome}`">
            <span class="num">{{ run.summary }}</span>
            <span v-if="run.notes" class="muted">{{ run.notes }}</span>
          </li>
        </ol>
      </section>

      <LiveNotice :message="scrapError[card.sheet.id] ?? ''" />

      <SheetRunForm
        v-if="running === card.sheet.id"
        :sheet="card.sheet"
        @recorded="closeRunForm(card.sheet.id)"
        @cancel="closeRunForm(card.sheet.id)"
      />
      <div v-else-if="card.sheet.status === 'planned'" class="form-actions">
        <button :id="`run-${card.sheet.id}`" type="button" class="btn" @click="running = card.sheet.id">{{ t("production.sheet.recordRun") }}</button>
        <template v-if="confirmingScrap === card.sheet.id">
          <span class="muted">{{ t("production.sheet.scrapWarning") }}</span>
          <button type="button" class="btn danger" :disabled="scrapping" @click="scrap(card.sheet.id)">
            {{ t("production.sheet.confirmScrap") }}
          </button>
          <button :id="`scrap-cancel-${card.sheet.id}`" type="button" class="btn" @click="cancelScrap(card.sheet.id)">
            {{ t("production.sheet.cancelScrap") }}
          </button>
        </template>
        <button v-else :id="`scrap-${card.sheet.id}`" type="button" class="btn" :disabled="scrapping" @click="scrap(card.sheet.id)">
          {{ t("production.sheet.scrap") }}
        </button>
      </div>
    </li>
  </ul>
  <div v-if="!production.loadError && production.hasMore" class="more">
    <span class="muted num">{{ t("production.list.showing", { shown: production.sheets.length, total: production.total }) }}</span>
    <button type="button" class="btn" :disabled="production.loading || production.loadingMore" @click="production.loadMore()">
      {{ production.loadingMore ? t("production.list.loadingMore") : t("production.list.loadMore") }}
    </button>
  </div>
</template>

<style scoped>
.plan { display: grid; grid-template-columns: minmax(220px, 1fr) auto; align-items: end; gap: 12px 16px; margin-block-end: 20px; }
.plan .notice { grid-column: 1 / -1; }
@media (max-width: 520px) { .plan { grid-template-columns: 1fr; } }
.head { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; margin-block-end: 12px; }
.used { margin-inline-start: auto; font-size: 15px; }
/* حبّة الحالة كما في الدليل: خلفية ناعمة ونص بحبر النص. */
.state { padding: 2px 10px; border-radius: 999px; font-size: 13px; white-space: nowrap; background: var(--warm-soft); color: var(--ink); }
.state.is-done { background: var(--ok-soft); }
.state.is-scrapped { background: var(--risk-soft); color: var(--risk); }
.legend { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 4px; font-size: 15px; }
.legend li { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.tag {
  display: inline-flex; align-items: center; justify-content: center; min-inline-size: 26px; block-size: 26px;
  border: 1px solid var(--accent); border-radius: var(--radius); color: var(--accent); font-weight: 600;
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
