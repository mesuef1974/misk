import { ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { catalogService, type Material, type ProductTemplate } from "@/services/catalog";

export const useCatalogStore = defineStore("catalog", () => {
  const materials = ref<Material[]>([]);
  const templates = ref<ProductTemplate[]>([]);
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

  return { materials, templates, loading, loaded, loadError, load, ensureLoaded, templateBySlug, materialById };
});
