<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import OrderStatusBadge from "@/components/OrderStatusBadge.vue";
import { formatDate, formatMoney, ORDER_STATUSES, STATUS_LABELS } from "@/domain/orders";
import { useOrdersStore } from "@/stores/orders";

const store = useOrdersStore();
const filter = ref("");

// الأعداد والتصفية من الخادم: القائمة صفحات، وما حُمّل منها ليس الجدول كله.
const filters = computed(() => [
  { value: "", label: "الكل", count: store.totalAll },
  ...ORDER_STATUSES.map((status) => ({
    value: status as string,
    label: STATUS_LABELS[status],
    count: store.countByStatus[status] ?? 0,
  })),
]);

function choose(value: string): Promise<void> {
  filter.value = value;
  return store.load(value);
}

onMounted(() => store.load());
</script>

<template>
  <div class="page-head">
    <h1>الطلبات</h1>
    <RouterLink class="btn primary" :to="{ name: 'order-new' }">طلب جديد</RouterLink>
  </div>

  <div class="filters" role="group" aria-label="تصفية بالحالة">
    <button
      v-for="option in filters"
      :key="option.value"
      type="button"
      class="chip"
      :class="{ active: filter === option.value }"
      :aria-pressed="filter === option.value"
      @click="choose(option.value)"
    >
      {{ option.label }} <span class="count">{{ option.count }}</span>
    </button>
  </div>

  <div v-if="store.loadError" class="notice" role="alert">
    {{ store.loadError }}
    <button type="button" class="btn retry" @click="store.load(filter)">إعادة المحاولة</button>
  </div>
  <p v-else-if="store.loading && !store.loaded" class="muted" role="status">يحمّل الطلبات…</p>
  <p v-else-if="store.totalAll === 0" class="panel muted">لا طلبات بعد. ابدأ بـ«طلب جديد».</p>
  <p v-else-if="store.orders.length === 0" class="panel muted">لا طلبات بهذه الحالة.</p>

  <ul v-if="!store.loadError && store.orders.length > 0" class="orders" :aria-busy="store.loading">
    <li v-for="order in store.orders" :key="order.id">
      <RouterLink class="order" :to="{ name: 'order-detail', params: { id: order.id } }">
        <span class="who">
          <strong>{{ order.customer_name }}</strong>
          <span class="muted">طلب {{ order.id }} · {{ order.items.length }} بند</span>
        </span>
        <span v-if="order.occasion_date" class="muted">المناسبة: {{ formatDate(order.occasion_date) }}</span>
        <OrderStatusBadge :status="order.status" />
        <span class="total">{{ formatMoney(order.total) }}</span>
      </RouterLink>
    </li>
  </ul>
  <div v-if="!store.loadError && store.hasMore" class="more">
    <span class="muted num">يعرض {{ store.orders.length }} من {{ store.total }}</span>
    <button type="button" class="btn" :disabled="store.loadingMore" @click="store.loadMore()">
      {{ store.loadingMore ? "يحمّل…" : "تحميل المزيد" }}
    </button>
  </div>
</template>

<style scoped>
.retry { margin-inline-start: 12px; }
.orders { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.order {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 12px 16px;
  border: 1px solid var(--line); border-radius: 10px; background: var(--surface);
  color: var(--ink); text-decoration: none;
}
.order:hover { border-color: var(--accent); }
.who { display: flex; flex-direction: column; flex: 1 1 220px; min-inline-size: 0; line-height: 1.5; }
.who .muted { font-size: 14px; }
.total { font-weight: 600; font-variant-numeric: tabular-nums; min-inline-size: 110px; text-align: end; }
</style>
