import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiError, errorMessage } from "@/api/client";
import { appendPage } from "@/api/paging";
import { i18n } from "@/i18n";
import arProduction from "@/i18n/locales/ar/production";
import {
  productionService,
  type PlanJob,
  type PlanOutcome,
  type Run,
  type RunDraft,
  type Sheet,
} from "@/services/production";

/** فترات استطلاع مهمة التخطيط: سريعة أولًا ثم كل ثلاث ثوانٍ، ودقيقتان حدًّا (مهلة العامل خمس دقائق). */
export const PLAN_POLL_MS = [500, 1000, 1000, 2000, 2000, ...Array<number>(38).fill(3000)];
/** النص العربي لرسالة انتهاء المهلة (للاختبارات)؛ ما يُعرض يأتي من `production.plan.timeout` بلغة الصفحة. */
export const PLAN_TIMEOUT_MESSAGE = arProduction.plan.timeout;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** أخطاء الاتصال والبوابة عابرة: المهمة ماضية في العامل، فيُعاد الاستطلاع في موعده التالي. */
const TRANSIENT = new Set([0, 502, 503, 504]);

/** أُوقف انتظار التخطيط (مغادرة الصفحة أو الخروج). المهمة ماضية في الخادم، وألواحها تظهر عند التحميل التالي. */
export class PlanCancelled extends Error {
  constructor() {
    super("أُوقف انتظار التخطيط");
    this.name = "PlanCancelled";
  }
}

/** ينتظر مهمة التخطيط حتى تنتهي. معرّف مجهول يبقى `pending` في الخادم، فالحدّ هنا لا هناك.
 *  `alive` يُسأل بعد كل انتظار وكل رد: إن صار كاذبًا توقّف الاستطلاع. */
async function settled(job: PlanJob, alive: () => boolean): Promise<PlanOutcome> {
  for (const delay of PLAN_POLL_MS) {
    if (job.status !== "pending") break;
    await wait(delay);
    if (!alive()) throw new PlanCancelled();
    try {
      job = await productionService.planJob(job.id);
    } catch (error) {
      if (!(error instanceof ApiError && TRANSIENT.has(error.status))) throw error;
    }
  }
  // أُوقف أثناء آخر رد: لا 504 ولا 422 تعيد الصفحة المُزالة إلى التحميل.
  if (!alive()) throw new PlanCancelled();
  if (job.status === "failed") throw new ApiError(422, job.error);
  if (job.status === "pending") throw new ApiError(504, i18n.global.t("production.plan.timeout"));
  return { sheets: job.sheets, waiting: job.waiting };
}

export const useProductionStore = defineStore("production", () => {
  /** ما حُمّل من صفحات التصفية الحالية، الأحدث أولًا. */
  const sheets = ref<Sheet[]>([]);
  /** الحالة التي حُمّلت القائمة بها؛ فارغ = كل الحالات. */
  const status = ref("");
  /** كل ما يطابق التصفية في الخادم. */
  const total = ref(0);
  /** عدد الألواح لكل حالة في الخادم كله، لا في ما حُمّل. */
  const countByStatus = ref<Record<string, number>>({});
  const loading = ref(false);
  const loadingMore = ref(false);
  const loaded = ref(false);
  const loadError = ref("");
  let latest = 0;
  /** التصفية التي طلبها آخر تحميل، وإن لم يصل رده بعد. */
  let requested = "";
  /** يزيد عند إيقاف التخطيط أو المسح: تخطيط بدأ قبله لا يستطلع ولا يكتب في القائمة. */
  let planGeneration = 0;

  /** هل يدخل لوح بهذه الحالة في التصفية المحمّلة؟ */
  const matches = (sheetStatus: string) => status.value === "" || status.value === sheetStatus;

  /** لوح غيّر حالته فخرج من التصفية: يُرفع من القائمة كما لو أُعيد التحميل. */
  function dropIfFiltered(sheetId: number, sheetStatus: string): void {
    if (matches(sheetStatus)) return;
    sheets.value = sheets.value.filter((candidate) => candidate.id !== sheetId);
    total.value = Math.max(0, total.value - 1);
  }

  const totalAll = computed(() => Object.values(countByStatus.value).reduce((sum, count) => sum + count, 0));
  const hasMore = computed(() => sheets.value.length < total.value);

  /** الصفحة الأولى بتصفية الحالة. رد طلب أقدم يُهمل إن سبقه طلب أحدث. */
  async function load(forStatus = ""): Promise<void> {
    const ticket = ++latest;
    requested = forStatus;
    loading.value = true;
    loadError.value = "";
    try {
      const page = await productionService.sheets({ status: forStatus });
      if (ticket !== latest) return;
      sheets.value = page.items;
      status.value = forStatus;
      total.value = page.count;
      countByStatus.value = page.counts;
      loaded.value = true;
    } catch (error) {
      if (ticket === latest) loadError.value = errorMessage(error);
    } finally {
      if (ticket === latest) loading.value = false;
    }
  }

  /** لا يعمل أثناء تحميل تصفية جديدة: الحالة والإزاحة ما زالتا للتصفية القديمة. */
  async function loadMore(): Promise<void> {
    if (loading.value || loadingMore.value || !hasMore.value) return;
    const ticket = latest;
    loadingMore.value = true;
    loadError.value = "";
    try {
      const page = await productionService.sheets({ status: status.value, offset: sheets.value.length });
      if (ticket !== latest) return;
      sheets.value = appendPage(sheets.value, page.items);
      total.value = page.count;
      countByStatus.value = page.counts;
    } catch (error) {
      if (ticket === latest) loadError.value = errorMessage(error);
    } finally {
      loadingMore.value = false;
    }
  }

  async function ensureLoaded(): Promise<void> {
    if (!loaded.value && !loading.value) await load();
  }

  /** يعكس تغيّر حالة لوح في الأعداد بلا إعادة تحميل. */
  function moved(from: string | null, to: string, by = 1): void {
    const counts = { ...countByStatus.value };
    if (from) counts[from] = Math.max(0, (counts[from] ?? 0) - by);
    counts[to] = (counts[to] ?? 0) + by;
    countByStatus.value = counts;
  }

  // الكتابة ترمي الخطأ للصفحة لتعرضه بجانب الإجراء الذي سبّبه.

  /** الألواح الجديدة في أول القائمة (الأحدث أولًا كترتيب الخادم)، فارغة حين لا جديد، مع عدد ألواح المادة التي تنتظر القصّ.
   *  الخادم يخطّط في الطلب نفسه أو في عامل خلفي؛ في الثاني تُستطلع المهمة حتى تنتهي.
   *  إن بدأ تحميل (أو تحميل المزيد) أثناء التخطيط فقد يحمل الألواح الجديدة أو لا يحملها، وسيكتب فوق القائمة والأعداد:
   *  دمجها هنا يعدّها مرتين أو يضيع، فيُعاد التحميل بالتصفية المطلوبة بعد التثبيت ليحكم وحده. */
  async function plan(materialId: number): Promise<PlanOutcome> {
    const generation = planGeneration;
    const alive = () => generation === planGeneration;
    const ticket = latest;
    const job = await productionService.plan(materialId);
    if (!alive()) throw new PlanCancelled();
    const outcome = await settled(job, alive);
    const planned = outcome.sheets;
    if (!alive()) throw new PlanCancelled();
    if (planned.length > 0 && (ticket !== latest || loading.value || loadingMore.value)) {
      await load(requested);
      return outcome;
    }
    moved(null, "planned", planned.length);
    // الجديد مخطَّط: تصفية بحالة أخرى لا تعرضه.
    if (matches("planned")) {
      const fresh = new Set(planned.map((sheet) => sheet.id));
      const added = planned.filter((sheet) => !sheets.value.some((existing) => existing.id === sheet.id));
      sheets.value = [...planned, ...sheets.value.filter((sheet) => !fresh.has(sheet.id))];
      total.value += added.length;
    }
    return outcome;
  }

  /** يوقف استطلاع التخطيط الجاري؛ الصفحة تستدعيه عند مغادرتها. */
  function stopPlanning(): void {
    planGeneration += 1;
  }

  /** السجل يدخل تاريخ اللوح، والتشغيل الناجح يغلقه في الخادم؛ نعكس ذلك هنا بلا إعادة تحميل. */
  async function recordRun(sheetId: number, draft: RunDraft, requestId: string): Promise<Run> {
    const run = await productionService.recordRun(sheetId, draft, requestId);
    const sheet = sheets.value.find((candidate) => candidate.id === run.sheet_id);
    if (sheet && !sheet.runs.some((existing) => existing.id === run.id)) {
      sheet.runs.unshift(run);
      if (run.outcome === "ok" && sheet.status === "planned") {
        sheet.status = "done";
        moved("planned", "done");
        dropIfFiltered(sheet.id, "done");
      }
    }
    return run;
  }

  /** الإتلاف يرفع القطع عن اللوح في الخادم لتُخطَّط على لوح جديد. */
  async function scrap(sheetId: number): Promise<Sheet> {
    const scrapped = await productionService.scrap(sheetId);
    const index = sheets.value.findIndex((candidate) => candidate.id === scrapped.id);
    if (index !== -1) {
      if (sheets.value[index].status !== scrapped.status) moved(sheets.value[index].status, scrapped.status);
      sheets.value[index] = scrapped;
      dropIfFiltered(scrapped.id, scrapped.status);
    }
    return scrapped;
  }

  function clear(): void {
    latest += 1;
    stopPlanning();
    loading.value = false;
    sheets.value = [];
    status.value = "";
    total.value = 0;
    countByStatus.value = {};
    loaded.value = false;
    loadError.value = "";
  }

  return {
    sheets,
    status,
    total,
    totalAll,
    hasMore,
    loading,
    loadingMore,
    loaded,
    loadError,
    countByStatus,
    load,
    loadMore,
    ensureLoaded,
    plan,
    stopPlanning,
    recordRun,
    scrap,
    clear,
  };
});
