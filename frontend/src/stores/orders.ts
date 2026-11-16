import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { errorMessage } from "@/api/client";
import { ordersService, type Order, type OrderDraft } from "@/services/orders";

export const useOrdersStore = defineStore("orders", () => {
  const orders = ref<Order[]>([]);
  const loading = ref(false);
  const loaded = ref(false);
  const loadError = ref("");

  const countByStatus = computed(() => {
    const counts: Record<string, number> = {};
    for (const order of orders.value) counts[order.status] = (counts[order.status] ?? 0) + 1;
    return counts;
  });

  function byId(orderId: number): Order | undefined {
    return orders.value.find((order) => order.id === orderId);
  }

  /** يضع الطلب في موضعه إن كان موجودًا، وإلا في أول القائمة (الأحدث أولًا كترتيب الخادم). */
  function upsert(order: Order): Order {
    const index = orders.value.findIndex((existing) => existing.id === order.id);
    if (index === -1) orders.value.unshift(order);
    else orders.value[index] = order;
    return order;
  }

  async function load(): Promise<void> {
    loading.value = true;
    loadError.value = "";
    try {
      orders.value = await ordersService.list();
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
  async function create(draft: OrderDraft): Promise<Order> {
    return upsert(await ordersService.create(draft));
  }

  async function transition(orderId: number, toStatus: string): Promise<Order> {
    return upsert(await ordersService.transition(orderId, toStatus));
  }

  return { orders, loading, loaded, loadError, countByStatus, byId, load, ensureLoaded, create, transition };
});
