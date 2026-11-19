import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiError, errorMessage } from "@/api/client";
import { appendPage } from "@/api/paging";
import { productionService, type PlanJob, type Run, type RunDraft, type Sheet } from "@/services/production";

/** فترات استطلاع مهمة التخطيط: سريعة أولًا ثم كل ثلاث ثوانٍ، ودقيقتان حدًّا (مهلة العامل خمس دقائق). */
export const PLAN_POLL_MS = [500, 1000, 1000, 2000, 2000, ...Array<number>(38).fill(3000)];
export const PLAN_TIMEOUT_MESSAGE = "التخطيط يستغرق أطول من المعتاد. حدّث الصفحة بعد قليل لترى الألواح.";

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** أخطاء الاتصال والبوابة عابرة: المهمة ماضية في العامل، فيُعاد الاستطلاع في موعده التالي. */
const TRANSIENT = new Set([0, 502, 503, 504]);

/** ينتظر مهمة التخطيط حتى تنتهي. معرّف مجهول يبقى `pending` في الخادم، فالحدّ هنا لا هناك. */
async function settled(job: PlanJob): Promise<Sheet[]> {
  for (const delay of PLAN_POLL_MS) {
    if (job.status !== "pending") break;
    await wait(delay);
    try {
      job = await productionService.planJob(job.id);
    } catch (error) {
      if (!(error instanceof ApiError && TRANSIENT.has(error.status))) throw error;
    }
  }
  if (job.status === "failed") throw new ApiError(422, job.error);
  if (job.status === "pending") throw new ApiError(504, PLAN_TIMEOUT_MESSAGE);
  return job.sheets;
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

  const totalAll = computed(() => Object.values(countByStatus.value).reduce((sum, count) => sum + count, 0));
  const hasMore = computed(() => sheets.value.length < total.value);

  /** الصفحة الأولى بتصفية الحالة. رد طلب أقدم يُهمل إن سبقه طلب أحدث. */
  async function load(forStatus = ""): Promise<void> {
    const ticket = ++latest;
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

  /** الألواح الجديدة في أول القائمة (الأحدث أولًا كترتيب الخادم). قائمة فارغة حين لا قطع تنتظر.
   *  الخادم يخطّط في الطلب نفسه أو في عامل خلفي؛ في الثاني تُستطلع المهمة حتى تنتهي. */
  async function plan(materialId: number): Promise<Sheet[]> {
    const planned = await settled(await productionService.plan(materialId));
    const fresh = new Set(planned.map((sheet) => sheet.id));
    sheets.value = [...planned, ...sheets.value.filter((sheet) => !fresh.has(sheet.id))];
    total.value += planned.length;
    moved(null, "planned", planned.length);
    return planned;
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
    }
    return scrapped;
  }

  function clear(): void {
    latest += 1;
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
    recordRun,
    scrap,
    clear,
  };
});
