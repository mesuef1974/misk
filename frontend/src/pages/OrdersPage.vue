<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import OrderStatusBadge from "@/components/OrderStatusBadge.vue";
import { formatDate, formatMoney, ORDER_STATUSES, STATUS_LABELS } from "@/domain/orders";
import { useOrdersStore } from "@/stores/orders";

const store = useOrdersStore();
const filter = ref("");

const filters = computed(() => [
  { value: "", label: "الكل", count: store.orders.length },
  ...ORDER_STATUSES.map((status) => ({
    value: status as string,
    label: STATUS_LABELS[status],
    count: store.countByStatus[status] ?? 0,
  })),
]);
const visible = computed(() =>
  filter.value ? store.orders.filter((order) => order.status === filter.value) : store.orders,
);

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
      @click="filter = option.value"
    >
      {{ option.label }} <span class="count">{{ option.count }}</span>
    </button>
  </div>

  <div v-if="store.loadError" class="notice" role="alert">
    {{ store.loadError }}
    <button type="button" class="btn retry" @click="store.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="store.loading && !store.loaded" class="muted" role="status">يحمّل الطلبات…</p>
  <p v-else-if="store.orders.length === 0" class="panel muted">لا طلبات بعد. ابدأ بـ«طلب جديد».</p>
  <p v-else-if="visible.length === 0" class="panel muted">لا طلبات بهذه الحالة.</p>

  <ul v-else class="orders">
    <li v-for="order in visible" :key="order.id">
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
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-block-end: 16px; }
.chip {
  min-block-size: 40px; padding-inline: 14px; border: 1px solid var(--line); border-radius: 999px;
  background: var(--surface); color: var(--muted); font: inherit; font-size: 15px; cursor: pointer;
}
.chip.active { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.count { font-variant-numeric: tabular-nums; opacity: 0.75; }
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
