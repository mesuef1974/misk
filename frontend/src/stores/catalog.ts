import { ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import {
  catalogService,
  type Calibration,
  type CalibrationDraft,
  type Material,
  type MaterialDraft,
  type ProductTemplate,
  type TemplateDraft,
} from "@/services/catalog";

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, "ar");

export const useCatalogStore = defineStore("catalog", () => {
  const materials = ref<Material[]>([]);
  const templates = ref<ProductTemplate[]>([]);
  /** معايرات كل مادة بمعرّفها؛ تُجلب عند فتح المادة لا مع الكتالوج. */
  const calibrations = ref<Record<number, Calibration[]>>({});
  const loading = ref(false);
  const loaded = ref(false);
  const loadError = ref("");

  async function load(): Promise<void> {
    loading.value = true;
    loadError.value = "";
    try {
      [materials.value, templates.value] = await Promise.all([
        catalogService.materials(),
        catalogService.templates(),
      ]);
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

  function templateBySlug(slug: string): ProductTemplate | undefined {
    return templates.value.find((template) => template.slug === slug);
  }

  function materialById(materialId: number): Material | undefined {
    return materials.value.find((material) => material.id === materialId);
  }

  /** يضع العنصر مكان سابقه بالمعرّف أو يضيفه، ويبقي الترتيب بالاسم كترتيب الخادم. */
  function place<T extends { id: number; name: string }>(list: T[], saved: T): T[] {
    return [...list.filter((existing) => existing.id !== saved.id), saved].sort(byName);
  }

  // الكتابة ترمي الخطأ للصفحة لتعرضه بجانب النموذج الذي سبّبه.
  async function saveMaterial(draft: MaterialDraft): Promise<Material> {
    const saved = await catalogService.saveMaterial(draft);
    materials.value = place(materials.value, saved);
    return saved;
  }

  async function saveTemplate(draft: TemplateDraft): Promise<ProductTemplate> {
    const saved = await catalogService.saveTemplate(draft);
    templates.value = place(templates.value, saved);
    return saved;
  }

  async function loadCalibrations(materialId: number): Promise<Calibration[]> {
    const rows = await catalogService.calibrations(materialId);
    calibrations.value[materialId] = rows;
    return rows;
  }

  /** الخادم يعيد السجل الموجود لقياس مكرر في اليوم نفسه، فلا يُضاف مرتين هنا أيضًا. */
  async function addCalibration(materialId: number, draft: CalibrationDraft): Promise<Calibration> {
    const saved = await catalogService.addCalibration(materialId, draft);
    const rows = calibrations.value[materialId] ?? [];
    if (!rows.some((row) => row.id === saved.id)) calibrations.value[materialId] = [saved, ...rows];
    return saved;
  }

  function clear(): void {
    materials.value = [];
    templates.value = [];
    calibrations.value = {};
    loaded.value = false;
    loadError.value = "";
  }

  return {
    materials,
    templates,
    calibrations,
    loading,
    loaded,
    loadError,
    load,
    ensureLoaded,
    templateBySlug,
    materialById,
    saveMaterial,
    saveTemplate,
    loadCalibrations,
    addCalibration,
    clear,
  };
});
