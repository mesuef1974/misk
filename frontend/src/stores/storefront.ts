import { ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { storeService, type StoreTemplate } from "@/services/store";

/** المنتجات المعروضة للبيع: تُجلب مرة وتشترك فيها الرئيسية وصفحة المنتجات واقتراحات المصمِّم. */
export const useStorefrontStore = defineStore("storefront", () => {
  const templates = ref<StoreTemplate[]>([]);
  const loading = ref(false);
  const loaded = ref(false);
  const loadError = ref("");
  let pending: Promise<void> | null = null;

  function load(): Promise<void> {
    pending ??= (async () => {
      loading.value = true;
      loadError.value = "";
      try {
        templates.value = await storeService.templates();
        loaded.value = true;
      } catch (error) {
        loadError.value = errorMessage(error);
      } finally {
        loading.value = false;
        pending = null;
      }
    })();
    return pending;
  }

  function ensureLoaded(): Promise<void> {
    return loaded.value ? Promise.resolve() : load();
  }

  function bySlug(slug: string): StoreTemplate | undefined {
    return templates.value.find((template) => template.slug === slug);
  }

  return { templates, loading, loaded, loadError, load, ensureLoaded, bySlug };
});
