<script setup lang="ts">
// السلة: بنودها ومجموعها وأقرب جاهزية. حالتها في الخادم، وكل تعديل يعيد السلة كما صارت.
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import LiveNotice from "@/components/LiveNotice.vue";
import { formatMoney } from "@/domain/orders";
import { formatDay, lineName, localized, safePaymentUrl, storeError } from "@/domain/store";
import type { CartItem } from "@/services/store";
import { useCartStore } from "@/stores/cart";

const MAX_QUANTITY = 50; // نسخة الواجهة من MAX_LINE_QUANTITY في apps/checkout/cart.py

const { t } = useI18n();
const cart = useCartStore();
const busy = ref<number | null>(null);
const notice = ref("");

const view = computed(() => cart.cart);
const paymentUrl = computed(() => safePaymentUrl(view.value?.payment_url));

onMounted(() => cart.load());

const itemName = (item: CartItem) => lineName(item);

/** قيم الحقول كما كتبها العميل، بترتيب المخطط المحفوظ؛ المنطقي والفارغ لا يُعرضان. */
function paramsText(item: CartItem): string {
  return Object.values(item.params)
    .filter((value) => typeof value !== "boolean" && value !== "")
    .join(" · ");
}

async function change(action: () => Promise<void>, itemId: number): Promise<void> {
  busy.value = itemId;
  notice.value = "";
  try {
    await action();
  } catch (error) {
    notice.value = storeError(error, t("errors.unexpected")).message;
    // الخادم رفض: تُعاد السلة كما هي عنده كي لا يبقى في الحقل رقم لم يُحفظ.
    await cart.load();
  } finally {
    busy.value = null;
  }
}

function setQuantity(item: CartItem, event: Event): void {
  const input = event.target as HTMLInputElement;
  const quantity = Number(input.value);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > MAX_QUANTITY) {
    input.value = String(item.quantity);
    return;
  }
  if (quantity !== item.quantity) void change(() => cart.setQuantity(item.id, quantity), item.id);
}
</script>

<template>
  <h1>{{ t("store.cart.heading") }}</h1>

  <div v-if="cart.loadError" class="notice" role="alert">
    {{ cart.loadError }}
    <button type="button" class="btn retry" @click="cart.load()">{{ t("store.products.retry") }}</button>
  </div>

  <p v-else-if="!view" class="muted">{{ t("store.cart.loading") }}</p>

  <div v-else-if="view.items.length === 0" class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ t("store.cart.empty") }}</p>
      <RouterLink class="btn primary browse" :to="{ name: 'products' }">{{ t("store.cart.browse") }}</RouterLink>
    </div>
  </div>

  <template v-else>
    <div v-if="cart.locked" class="notice ok locked">
      <span>{{ t("store.cart.locked") }}</span>
      <a v-if="paymentUrl" class="btn primary" :href="paymentUrl">{{ t("store.cart.payNow") }}</a>
    </div>
    <LiveNotice :message="notice" />

    <ul class="cards">
      <li v-for="item in view.items" :key="item.id" class="list-row line">
        <span class="what">
          <b>{{ itemName(item) }}</b>
          <span class="muted">{{ localized(item.material_name, item.material_name_en) }}</span>
          <span v-if="paramsText(item)" class="text" dir="auto">{{ paramsText(item) }}</span>
          <span v-if="item.needs_review" class="pill">{{ t("store.cart.review") }}</span>
        </span>
        <label class="qty">
          <span class="muted">{{ t("store.cart.quantity") }}</span>
          <input
            type="number"
            min="1"
            :max="MAX_QUANTITY"
            step="1"
            inputmode="numeric"
            :value="item.quantity"
            :disabled="cart.locked || busy === item.id"
            :aria-label="t('store.cart.quantityOf', { name: itemName(item) })"
            @change="setQuantity(item, $event)"
          />
        </label>
        <b class="num sum">{{ formatMoney(item.line_total) }}</b>
        <button
          type="button"
          class="btn danger"
          :disabled="cart.locked || busy === item.id"
          :aria-label="t('store.cart.removeOf', { name: itemName(item) })"
          @click="change(() => cart.remove(item.id), item.id)"
        >
          {{ t("store.cart.remove") }}
        </button>
      </li>
    </ul>

    <section class="panel summary">
      <dl class="sums">
        <div><dt>{{ t("store.cart.subtotal") }}</dt><dd class="num">{{ formatMoney(view.subtotal) }}</dd></div>
        <div v-if="Number(view.delivery_fee) > 0"><dt>{{ t("store.cart.deliveryFee") }}</dt><dd class="num">{{ formatMoney(view.delivery_fee) }}</dd></div>
        <div class="grand"><dt>{{ t("store.cart.total") }}</dt><dd class="num">{{ formatMoney(view.total) }}</dd></div>
      </dl>
      <p class="ready">{{ view.ready_on ? t("store.cart.readyOn", { date: formatDay(view.ready_on) }) : t("store.cart.noCapacity") }}</p>
      <p v-if="view.needs_review" class="hint">{{ t("store.cart.needsReview") }}</p>
      <div class="form-actions">
        <RouterLink v-if="!cart.locked" class="btn primary" :to="{ name: 'checkout' }">{{ t("store.cart.checkout") }}</RouterLink>
        <RouterLink class="btn" :to="{ name: 'products' }">{{ t("store.cart.browse") }}</RouterLink>
      </div>
    </section>
  </template>
</template>

<style scoped>
.retry { margin-inline-start: 12px; }
.browse { margin-block-start: 16px; }
.locked { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.line .what { display: flex; flex-direction: column; gap: 2px; flex: 1 1 220px; min-inline-size: 0; line-height: 1.5; }
.line .what .muted { font-size: 14px; }
.line .text { overflow-wrap: anywhere; }
.line .pill { align-self: flex-start; }
.qty { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.qty input { inline-size: 84px; }
.sum { min-inline-size: 110px; text-align: end; }
.summary { display: flex; flex-direction: column; gap: 8px; max-inline-size: 520px; }
.summary p { margin: 0; }
.sums { margin: 0; display: grid; gap: 4px; }
.sums div { display: flex; justify-content: space-between; gap: 12px; }
.sums dd { margin: 0; }
.sums .grand { font-weight: 700; font-size: 18px; padding-block-start: 8px; border-block-start: 1px dashed var(--line); }
.ready { font-weight: 600; }
</style>
