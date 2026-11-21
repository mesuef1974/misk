<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { errorMessage } from "@/api/client";
import BrandIcon from "@/components/BrandIcon.vue";
import OrderStatusBadge from "@/components/OrderStatusBadge.vue";
import {
  formatDate,
  formatMoney,
  lineTotal,
  orderActions,
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
const settled = ref(false);
const lookupError = ref("");

const order = computed(() => orders.byId(props.orderId));
const actions = computed(() => (order.value ? orderActions(order.value) : []));

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

/** الطلب من المخزن إن كان فيه (جاء من القائمة أو أُنشئ للتو)، وإلا يُجلب وحده بلا تحميل القائمة كلها. */
async function lookup(): Promise<void> {
  lookupError.value = "";
  settled.value = false;
  try {
    if (!order.value) await orders.fetchOne(props.orderId);
  } catch (error) {
    lookupError.value = errorMessage(error);
  } finally {
    settled.value = true;
  }
}

onMounted(() => Promise.all([lookup(), catalog.ensureLoaded()]));
watch(() => props.orderId, lookup);

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

  <div v-if="lookupError" class="notice" role="alert">
    {{ lookupError }}
    <button type="button" class="btn retry" @click="lookup()">إعادة المحاولة</button>
  </div>
  <p v-else-if="!order && !settled" class="muted" role="status">يحمّل الطلب…</p>
  <p v-else-if="!order" class="panel muted">لا طلب بهذا الرقم.</p>

  <template v-else>
    <section class="panel summary">
      <div>
        <span class="muted">العميل</span>
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

    <section v-if="order.notes" class="panel order-notes">
      <span class="muted">ملاحظات</span>
      <p>{{ order.notes }}</p>
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
        <BrandIcon name="delivery" v-if="status === 'delivered'" />
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
.order-notes .muted { font-size: 14px; }
.order-notes p { margin: 2px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }
h2 { font-size: 20px; margin: 0; }
.lines { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.line { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; }
.what { display: flex; flex-direction: column; flex: 1 1 260px; min-inline-size: 0; line-height: 1.6; }
.price { display: flex; flex-direction: column; align-items: end; line-height: 1.6; }
dl { display: grid; grid-template-columns: auto 1fr; gap: 0 12px; margin-block: 6px 0; font-size: 15px; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.num { font-variant-numeric: tabular-nums; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.retry { margin-inline-start: 12px; }
</style>
