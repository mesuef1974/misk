import { ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { storeService, type StoreDesign } from "@/services/store";

/** التصاميم الجاهزة المعروضة: تُجلب مرة عند أول فتح للصفحة. */
export const useDesignsStore = defineStore("designs", () => {
  const designs = ref<StoreDesign[]>([]);
  const loaded = ref(false);
  const loadError = ref("");
  let pending: Promise<void> | null = null;

  function load(): Promise<void> {
    pending ??= (async () => {
      loadError.value = "";
      try {
        designs.value = await storeService.designs();
        loaded.value = true;
      } catch (error) {
        loadError.value = errorMessage(error);
      } finally {
        pending = null;
      }
    })();
    return pending;
  }

  function ensureLoaded(): Promise<void> {
    return loaded.value ? Promise.resolve() : load();
  }

  return { designs, loaded, loadError, load, ensureLoaded };
});
