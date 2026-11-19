import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiError, errorMessage } from "@/api/client";
import { appendPage } from "@/api/paging";
import { ordersService, type Order, type OrderDraft } from "@/services/orders";

export const useOrdersStore = defineStore("orders", () => {
  /** ما حُمّل من صفحات التصفية الحالية، الأحدث أولًا. */
  const orders = ref<Order[]>([]);
  /** الحالة التي حُمّلت القائمة بها؛ فارغ = كل الحالات. */
  const status = ref("");
  /** كل ما يطابق التصفية في الخادم. */
  const total = ref(0);
  /** عدد الطلبات لكل حالة في الخادم كله، لا في ما حُمّل. */
  const countByStatus = ref<Record<string, number>>({});
  const loading = ref(false);
  const loadingMore = ref(false);
  const loaded = ref(false);
  const loadError = ref("");
  let latest = 0;
  /** يرتفع بـ clear() وحده (الخروج أو انتهاء الجلسة): رد كتابة بدأت قبله لا يعيد بيانات زبون إلى المخزن. */
  let generation = 0;

  const totalAll = computed(() => Object.values(countByStatus.value).reduce((sum, count) => sum + count, 0));
  const hasMore = computed(() => orders.value.length < total.value);

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

  /** الصفحة الأولى بتصفية الحالة. رد طلب أقدم يُهمل إن سبقه طلب أحدث (نقرات متتالية على التصفية). */
  async function load(forStatus = ""): Promise<void> {
    const ticket = ++latest;
    loading.value = true;
    loadError.value = "";
    try {
      const page = await ordersService.list({ status: forStatus });
      if (ticket !== latest) return;
      orders.value = page.items;
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
      const page = await ordersService.list({ status: status.value, offset: orders.value.length });
      if (ticket !== latest) return;
      orders.value = appendPage(orders.value, page.items);
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

  /** طلب واحد من الخادم، للرابط المباشر إلى طلب ليس في القائمة. undefined حين لا طلب بهذا الرقم. */
  async function fetchOne(orderId: number): Promise<Order | undefined> {
    const ticket = generation;
    try {
      return keep(ticket, await ordersService.get(orderId));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return undefined;
      throw error;
    }
  }

  /** يضع الطلب في المخزن إن لم يُمسح منذ بدأ الطلب، ويعيده في الحالتين ليعرضه المستدعي أو يتجاهله. */
  function keep(ticket: number, order: Order): Order {
    return ticket === generation ? upsert(order) : order;
  }

  function clear(): void {
    latest += 1;
    generation += 1;
    loading.value = false;
    orders.value = [];
    status.value = "";
    total.value = 0;
    countByStatus.value = {};
    loaded.value = false;
    loadError.value = "";
  }

  // الكتابة ترمي الخطأ للصفحة لتعرضه بجانب الإجراء الذي سبّبه.
  async function create(draft: OrderDraft): Promise<Order> {
    const ticket = generation;
    return keep(ticket, await ordersService.create(draft));
  }

  async function transition(orderId: number, toStatus: string): Promise<Order> {
    const ticket = generation;
    return keep(ticket, await ordersService.transition(orderId, toStatus));
  }

  return {
    orders,
    status,
    total,
    totalAll,
    hasMore,
    loading,
    loadingMore,
    loaded,
    loadError,
    countByStatus,
    byId,
    load,
    loadMore,
    ensureLoaded,
    fetchOne,
    clear,
    create,
    transition,
  };
});
