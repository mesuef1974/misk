<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { errorMessage } from "@/api/client";
import OrderStatusBadge from "@/components/OrderStatusBadge.vue";
import {
  formatDate,
  formatMoney,
  lineTotal,
  nextStatuses,
  TRANSITION_ACTIONS,
  type OrderStatus,
} from "@/domain/orders";
import { fieldLabel, type ParamValue } from "@/domain/params";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";

const props = defineProps<{ orderId: number }>();

const orders = useOrdersStore();
const catalog = useCatalogStore();

const busy = ref(false);
const actionError = ref("");
const confirmingCancel = ref(false);

const order = computed(() => orders.byId(props.orderId));
const actions = computed(() => (order.value ? nextStatuses(order.value.status) : []));

/** البنود جاهزة للعرض: أسماء القالب والمادة والمعاملات تُحسب هنا لا في القالب. */
const lines = computed(() =>
  (order.value?.items ?? []).map((item) => {
    const template = catalog.templateBySlug(item.template_slug);
    const labels = new Map((template?.param_schema ?? []).map((field) => [field.name, fieldLabel(field)]));
    return {
      id: item.id,
      template: template?.name ?? item.template_slug,
      material: catalog.materialById(item.material_id)?.name ?? `مادة ${item.material_id}`,
      params: Object.entries(item.params).map(([name, value]) => ({
        name,
        label: labels.get(name) ?? name,
        value: display(value),
      })),
      quantity: item.quantity,
      unitPrice: formatMoney(item.unit_price),
      total: formatMoney(lineTotal(item.quantity, item.unit_price)),
    };
  }),
);

function display(value: ParamValue): string {
  if (typeof value === "boolean") return value ? "نعم" : "لا";
  return String(value);
}

onMounted(() => Promise.all([orders.ensureLoaded(), catalog.ensureLoaded()]));

async function move(toStatus: OrderStatus): Promise<void> {
  // الإلغاء لا رجعة فيه: الضغطة الأولى تطلب التأكيد فقط.
  if (toStatus === "cancelled" && !confirmingCancel.value) {
    confirmingCancel.value = true;
    return;
  }
  confirmingCancel.value = false;
  actionError.value = "";
  busy.value = true;
  try {
    await orders.transition(props.orderId, toStatus);
  } catch (error) {
    actionError.value = errorMessage(error);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="page-head">
    <h1>طلب {{ orderId }}</h1>
    <RouterLink class="btn" :to="{ name: 'orders' }">رجوع للطلبات</RouterLink>
  </div>

  <div v-if="orders.loadError" class="notice" role="alert">
    {{ orders.loadError }}
    <button type="button" class="btn retry" @click="orders.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="!orders.loaded" class="muted" role="status">يحمّل الطلب…</p>
  <p v-else-if="!order" class="panel muted">لا طلب بهذا الرقم.</p>

  <template v-else>
    <section class="panel summary">
      <div>
        <span class="muted">الزبون</span>
        <strong>{{ order.customer_name }}</strong>
      </div>
      <div>
        <span class="muted">الحالة</span>
        <OrderStatusBadge :status="order.status" />
      </div>
      <div v-if="order.occasion_date">
        <span class="muted">تاريخ المناسبة</span>
        <strong>{{ formatDate(order.occasion_date) }}</strong>
      </div>
      <div>
        <span class="muted">المجموع</span>
        <strong class="num">{{ formatMoney(order.total) }}</strong>
      </div>
    </section>

    <h2>البنود</h2>
    <ul class="lines">
      <li v-for="line in lines" :key="line.id" class="panel line">
        <div class="what">
          <strong>{{ line.template }}</strong>
          <span class="muted">{{ line.material }}</span>
          <dl v-if="line.params.length">
            <template v-for="param in line.params" :key="param.name">
              <dt>{{ param.label }}</dt>
              <dd>{{ param.value }}</dd>
            </template>
          </dl>
        </div>
        <div class="price">
          <span class="muted num">{{ line.quantity }} × {{ line.unitPrice }}</span>
          <strong class="num">{{ line.total }}</strong>
        </div>
      </li>
    </ul>

    <div v-if="actionError" class="notice" role="alert">{{ actionError }}</div>

    <div v-if="actions.length" class="actions">
      <button
        v-for="status in actions"
        :key="status"
        type="button"
        class="btn"
        :class="status === 'cancelled' ? 'danger' : 'primary'"
        :disabled="busy"
        @click="move(status)"
      >
        {{ status === "cancelled" && confirmingCancel ? "اضغط ثانيةً لتأكيد الإلغاء" : TRANSITION_ACTIONS[status] }}
      </button>
      <button v-if="confirmingCancel" type="button" class="btn" @click="confirmingCancel = false">تراجع</button>
    </div>
    <p v-else class="muted">هذا الطلب في حالة نهائية ولا إجراء عليه.</p>
  </template>
</template>

<style scoped>
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px 24px; }
.summary > div { display: flex; flex-direction: column; align-items: start; gap: 2px; }
.summary .muted { font-size: 14px; }
h2 { font-size: 20px; margin-block: 24px 12px; }
.lines { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.line { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; }
.what { display: flex; flex-direction: column; flex: 1 1 260px; min-inline-size: 0; line-height: 1.6; }
.price { display: flex; flex-direction: column; align-items: end; line-height: 1.6; }
dl { display: grid; grid-template-columns: auto 1fr; gap: 0 12px; margin-block: 6px 0; font-size: 15px; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.num { font-variant-numeric: tabular-nums; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-block-start: 20px; }
.notice { margin-block-start: 16px; }
.retry { margin-inline-start: 12px; }
</style>
