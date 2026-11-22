import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { currentLocale } from "@/i18n";
import { storeService, type Cart, type CartItemDraft, type DesignItemDraft } from "@/services/store";

/** سلة الضيف: حالتها في الخادم (معرّفها في كوكي الجلسة)، وهذا المخزن نسخة العرض منها. */
export const useCartStore = defineStore("cart", () => {
  const cart = ref<Cart | null>(null);
  const loading = ref(false);
  const loadError = ref("");
  let pending: Promise<void> | null = null;

  const count = computed(() => (cart.value?.items ?? []).reduce((sum, item) => sum + item.quantity, 0));
  /** فُتحت صفحة الدفع: السلة مقفلة حتى يتم الدفع أو تنتهي مهلته. */
  const locked = computed(() => cart.value?.status === "awaiting_payment");

  /** النداءات المتزامنة (القشرة والصفحة معًا) تشترك في الطلب نفسه. */
  function load(): Promise<void> {
    pending ??= (async () => {
      loading.value = true;
      loadError.value = "";
      try {
        cart.value = await storeService.cart();
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
    return cart.value ? Promise.resolve() : load();
  }

  // الكتابة ترمي خطأها للصفحة: هي التي تعرضه بجانب ما سبّبه (حقل، بند، زر).
  async function add(draft: CartItemDraft): Promise<void> {
    cart.value = await storeService.addItem(draft, currentLocale());
  }

  async function addDesign(draft: DesignItemDraft): Promise<void> {
    cart.value = await storeService.addDesignItem(draft, currentLocale());
  }

  async function setQuantity(itemId: number, quantity: number): Promise<void> {
    cart.value = await storeService.setQuantity(itemId, quantity, currentLocale());
  }

  async function remove(itemId: number): Promise<void> {
    cart.value = await storeService.removeItem(itemId, currentLocale());
  }

  return { cart, loading, loadError, count, locked, load, ensureLoaded, add, addDesign, setQuantity, remove };
});
