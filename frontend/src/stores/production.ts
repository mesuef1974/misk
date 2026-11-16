import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { productionService, type Run, type RunDraft, type Sheet } from "@/services/production";

export const useProductionStore = defineStore("production", () => {
  const sheets = ref<Sheet[]>([]);
  const loading = ref(false);
  const loaded = ref(false);
  const loadError = ref("");

  const countByStatus = computed(() => {
    const counts: Record<string, number> = {};
    for (const sheet of sheets.value) counts[sheet.status] = (counts[sheet.status] ?? 0) + 1;
    return counts;
  });

  async function load(): Promise<void> {
    loading.value = true;
    loadError.value = "";
    try {
      sheets.value = await productionService.sheets();
      loaded.value = true;
    } catch (error) {
      loadError.value = errorMessage(error);
    } finally {
      loading.value = false;
    }
  }

  async function ensureLoaded(): Promise<void> {
    if (!loaded.value && !loading.value) await load();
  }

  // الكتابة ترمي الخطأ للصفحة لتعرضه بجانب الإجراء الذي سبّبه.

  /** الألواح الجديدة في أول القائمة (الأحدث أولًا كترتيب الخادم). قائمة فارغة حين لا قطع تنتظر. */
  async function plan(materialId: number): Promise<Sheet[]> {
    const planned = await productionService.plan(materialId);
    const fresh = new Set(planned.map((sheet) => sheet.id));
    sheets.value = [...planned, ...sheets.value.filter((sheet) => !fresh.has(sheet.id))];
    return planned;
  }

  /** التشغيل الناجح يغلق اللوح في الخادم؛ نعكس ذلك هنا بلا إعادة تحميل. */
  async function recordRun(sheetId: number, draft: RunDraft, requestId: string): Promise<Run> {
    const run = await productionService.recordRun(sheetId, draft, requestId);
    if (run.outcome === "ok") {
      const sheet = sheets.value.find((candidate) => candidate.id === run.sheet_id);
      if (sheet) sheet.status = "done";
    }
    return run;
  }

  function clear(): void {
    sheets.value = [];
    loaded.value = false;
    loadError.value = "";
  }

  return { sheets, loading, loaded, loadError, countByStatus, load, ensureLoaded, plan, recordRun, clear };
});
