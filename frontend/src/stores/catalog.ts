import { ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { currentLocale } from "@/i18n";
import {
  catalogService,
  type Calibration,
  type CalibrationDraft,
  type Material,
  type MaterialDraft,
  type ProductTemplate,
  type TemplateDraft,
} from "@/services/catalog";

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, currentLocale());

export const useCatalogStore = defineStore("catalog", () => {
  const materials = ref<Material[]>([]);
  const templates = ref<ProductTemplate[]>([]);
  /** معايرات كل مادة بمعرّفها؛ تُجلب عند فتح المادة لا مع الكتالوج. */
  const calibrations = ref<Record<number, Calibration[]>>({});
  const loading = ref(false);
  const loaded = ref(false);
  const loadError = ref("");
  /** يزيد عند المسح: رد طلب بدأ قبله (بعد الخروج) لا يكتب في المخزن. */
  let generation = 0;

  async function load(): Promise<void> {
    const ticket = generation;
    loading.value = true;
    loadError.value = "";
    try {
      const [loadedMaterials, loadedTemplates] = await Promise.all([
        catalogService.materials(),
        catalogService.templates(),
      ]);
      if (ticket !== generation) return;
      materials.value = loadedMaterials;
      templates.value = loadedTemplates;
      loaded.value = true;
    } catch (error) {
      if (ticket === generation) loadError.value = errorMessage(error);
    } finally {
      if (ticket === generation) loading.value = false;
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
    const ticket = generation;
    const saved = await catalogService.saveMaterial(draft);
    if (ticket === generation) materials.value = place(materials.value, saved);
    return saved;
  }

  async function saveTemplate(draft: TemplateDraft): Promise<ProductTemplate> {
    const ticket = generation;
    const saved = await catalogService.saveTemplate(draft);
    if (ticket === generation) templates.value = place(templates.value, saved);
    return saved;
  }

  async function loadCalibrations(materialId: number): Promise<Calibration[]> {
    const ticket = generation;
    const rows = await catalogService.calibrations(materialId);
    if (ticket === generation) calibrations.value[materialId] = rows;
    return rows;
  }

  /** الخادم يعيد السجل الموجود لقياس مكرر في اليوم نفسه، فلا يُضاف مرتين هنا أيضًا. */
  async function addCalibration(materialId: number, draft: CalibrationDraft): Promise<Calibration> {
    const ticket = generation;
    const saved = await catalogService.addCalibration(materialId, draft);
    if (ticket !== generation) return saved;
    const rows = calibrations.value[materialId] ?? [];
    if (!rows.some((row) => row.id === saved.id)) calibrations.value[materialId] = [saved, ...rows];
    return saved;
  }

  function clear(): void {
    generation += 1;
    loading.value = false;
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
