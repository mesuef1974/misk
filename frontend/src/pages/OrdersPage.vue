<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import BrandIcon from "@/components/BrandIcon.vue";
import OrderStatusBadge from "@/components/OrderStatusBadge.vue";
import { formatDate, formatMoney, ORDER_STATUSES, statusLabel, WORKSHOP_STATUSES } from "@/domain/orders";
import { useOrdersStore } from "@/stores/orders";

const { t } = useI18n();
const store = useOrdersStore();
const filter = ref("");

// الأعداد والتصفية من الخادم: القائمة صفحات، وما حُمّل منها ليس الجدول كله.
const filters = computed(() => [
  { value: "", label: t("orders.list.all"), count: store.totalAll },
  ...ORDER_STATUSES.map((status) => ({
    value: status as string,
    label: statusLabel(status),
    count: store.countByStatus[status] ?? 0,
  })).filter(
    (option) =>
      option.count > 0 || option.value === filter.value || (WORKSHOP_STATUSES as readonly string[]).includes(option.value),
  ),
]);

function choose(value: string): Promise<void> {
  filter.value = value;
  return store.load(value);
}

onMounted(() => store.load());
</script>

<template>
  <div class="page-head">
    <h1>{{ t("orders.list.heading") }}</h1>
    <RouterLink class="btn primary" :to="{ name: 'order-new' }">{{ t("orders.list.newOrder") }}</RouterLink>
  </div>

  <div class="filters" role="group" :aria-label="t('orders.list.filterLabel')">
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
    <button type="button" class="btn retry" @click="store.load(filter)">{{ t("orders.retry") }}</button>
  </div>
  <p v-else-if="store.loading && !store.loaded" class="muted" role="status">{{ t("orders.list.loading") }}</p>
  <div v-else-if="store.totalAll === 0" class="empty">
    <div class="inner"><div class="mark" aria-hidden="true"></div><p>{{ t("orders.list.empty") }}</p></div>
  </div>
  <p v-else-if="store.orders.length === 0" class="panel muted">{{ t("orders.list.emptyFiltered") }}</p>

  <ul v-if="!store.loadError && store.orders.length > 0" class="orders" :aria-busy="store.loading">
    <li v-for="order in store.orders" :key="order.id">
      <RouterLink class="list-row order" :to="{ name: 'order-detail', params: { id: order.id } }">
        <BrandIcon name="delivery" v-if="order.status === 'delivered'" />
        <BrandIcon name="order" v-else />
        <span class="who">
          <strong>{{ order.customer_name }}</strong>
          <span class="muted">{{ t("orders.list.rowMeta", { id: order.id, count: order.items.length }, order.items.length) }}</span>
        </span>
        <span v-if="order.occasion_date" class="muted">{{ t("orders.list.occasion", { date: formatDate(order.occasion_date) }) }}</span>
        <OrderStatusBadge :status="order.status" />
        <span class="total">{{ formatMoney(order.total) }}</span>
      </RouterLink>
    </li>
  </ul>
  <div v-if="!store.loadError && store.hasMore" class="more">
    <span class="muted num">{{ t("orders.list.showing", { shown: store.orders.length, total: store.total }) }}</span>
    <button type="button" class="btn" :disabled="store.loading || store.loadingMore" @click="store.loadMore()">
      {{ store.loadingMore ? t("orders.list.loadingMore") : t("orders.list.loadMore") }}
    </button>
  </div>
</template>

<style scoped>
.retry { margin-inline-start: 12px; }
.orders { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.who { display: flex; flex-direction: column; flex: 1 1 220px; min-inline-size: 0; line-height: 1.5; }
.who .muted { font-size: 13px; }
.total { font-weight: 600; font-variant-numeric: tabular-nums; min-inline-size: 110px; text-align: end; }
</style>
