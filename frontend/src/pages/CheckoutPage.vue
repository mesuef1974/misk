<script setup lang="ts">
// إتمام الطلب كضيف: الاسم وطريقة الاستلام، ثم فتح صفحة الدفع عند المزوّد.
// الطلب يصير مدفوعًا من إشعار البوابة لا من العودة من صفحتها؛ هنا يُسلَّم رابط التتبّع قبل الذهاب إليها.
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import LiveNotice from "@/components/LiveNotice.vue";
import { localToday } from "@/domain/catalog";
import { localizePath, type Locale } from "@/domain/locale";
import { formatMoney } from "@/domain/orders";
import { formatDay, formatMoment, localized, safePaymentUrl, storeError } from "@/domain/store";
import { currentLocale } from "@/i18n";
import { storeService, type CheckoutResult, type DeliveryZone, type Fulfillment } from "@/services/store";
import { useCartStore } from "@/stores/cart";

const SOURCES = ["instagram", "tiktok", "snapchat", "referral", "bazaar", "search"] as const;
const NAME_LENGTH = 120; // نسخة الواجهة من Customer.name
const NOTES_LENGTH = 2000;

const { t } = useI18n();
const cart = useCartStore();

const form = reactive({
  name: "",
  fulfillment: "pickup" as Fulfillment,
  zoneId: "" as number | "",
  occasion: "",
  notes: "",
  source: "",
});
const zones = ref<DeliveryZone[]>([]);
const errors = ref<Record<string, string>>({});
const notice = ref("");
const earliest = ref("");
const sending = ref(false);
const done = ref<CheckoutResult | null>(null);
const copied = ref(false);
const today = localToday();

const view = computed(() => cart.cart);
const zone = computed(() => zones.value.find((candidate) => candidate.id === form.zoneId));
const fee = computed(() => (form.fulfillment === "delivery" && zone.value ? Number(zone.value.fee) : 0));
const total = computed(() => Number(view.value?.subtotal ?? 0) + fee.value);
const readyOn = computed(() => earliest.value || view.value?.ready_on || "");
const paymentUrl = computed(() => safePaymentUrl(done.value?.payment_url));
const trackPath = computed(() => (done.value ? localizePath(`/track/${done.value.tracking_token}`, currentLocale() as Locale) : ""));
const trackUrl = computed(() => (trackPath.value ? window.location.origin + trackPath.value : ""));

onMounted(async () => {
  void cart.load();
  try {
    zones.value = await storeService.zones();
  } catch {
    // بلا مناطق يبقى الاستلام بموعد متاحًا، وخيار التوصيل معطَّل بسببه الظاهر.
  }
});

async function submit(): Promise<void> {
  errors.value = {};
  notice.value = "";
  earliest.value = "";
  const name = form.name.split(/\s+/).filter(Boolean).join(" ");
  if (!name) {
    errors.value = { customer_name: t("orders.validation.required") };
    return;
  }
  if (form.fulfillment === "delivery" && form.zoneId === "") {
    errors.value = { delivery_zone_id: t("orders.validation.required") };
    return;
  }
  sending.value = true;
  try {
    done.value = await storeService.checkout(
      {
        customer_name: name,
        fulfillment: form.fulfillment,
        occasion_date: form.occasion || null,
        notes: form.notes.trim(),
        source: form.source,
        delivery_zone_id: form.fulfillment === "delivery" && form.zoneId !== "" ? form.zoneId : null,
      },
      currentLocale(),
    );
    // السلة صارت «بانتظار الدفع»: تُحدَّث ليعرضها الشريط وصفحة السلة مقفلةً.
    void cart.load();
  } catch (error) {
    const failure = storeError(error, t("errors.unexpected"));
    errors.value = failure.fields;
    notice.value = failure.message;
    earliest.value = failure.readyOn ?? "";
    // السلة تغيّرت أو انتهت مهلتها في الخادم: تُعرض كما صارت.
    if (failure.code.startsWith("cart_") || failure.code === "design_changed") void cart.load();
  } finally {
    sending.value = false;
  }
}

async function copyLink(): Promise<void> {
  try {
    await navigator.clipboard.writeText(trackUrl.value);
    copied.value = true;
  } catch {
    // المتصفح منع الحافظة: الرابط ظاهر في الحقل ويُنسخ يدويًّا.
    copied.value = false;
  }
}
</script>

<template>
  <h1>{{ done ? t("store.checkout.done.heading") : t("store.checkout.heading") }}</h1>

  <section v-if="done" class="panel done">
    <p class="lead">{{ t("store.checkout.done.body") }}</p>
    <p class="num amount">{{ t("store.checkout.done.amount", { amount: formatMoney(done.amount) }) }}</p>
    <p class="hint">{{ t("store.checkout.done.expires", { time: formatMoment(done.expires_at) }) }}</p>
    <a v-if="paymentUrl" class="btn primary pay" :href="paymentUrl">{{ t("store.checkout.done.payNow") }}</a>

    <div class="track">
      <label class="field">
        <span>{{ t("store.checkout.done.trackHeading") }}</span>
        <input type="text" readonly dir="ltr" name="tracking-link" :value="trackUrl" @focus="($event.target as HTMLInputElement).select()" />
      </label>
      <p class="hint">{{ t("store.checkout.done.trackHint") }}</p>
      <div class="form-actions">
        <button type="button" class="btn" @click="copyLink">{{ t("store.checkout.done.copy") }}</button>
        <RouterLink class="btn" :to="{ name: 'track', params: { token: done.tracking_token } }">{{ t("store.checkout.done.open") }}</RouterLink>
      </div>
      <LiveNotice kind="status" :message="copied ? t('store.checkout.done.copied') : ''" />
    </div>
  </section>

  <p v-else-if="!view" class="muted">{{ cart.loadError || t("store.cart.loading") }}</p>

  <div v-else-if="view.items.length === 0 || cart.locked" class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ cart.locked ? t("store.cart.locked") : t("store.checkout.empty") }}</p>
      <RouterLink class="btn primary back" :to="{ name: cart.locked ? 'cart' : 'products' }">
        {{ cart.locked ? t("store.checkout.back") : t("store.cart.browse") }}
      </RouterLink>
    </div>
  </div>

  <div v-else class="layout">
    <form class="panel form" novalidate @submit.prevent="submit">
      <label class="field">
        <span>{{ t("store.checkout.name") }}</span>
        <input v-model="form.name" type="text" name="customer_name" autocomplete="name" :maxlength="NAME_LENGTH" :aria-invalid="Boolean(errors.customer_name)" />
        <span v-if="errors.customer_name" class="error">{{ errors.customer_name }}</span>
        <span v-else class="hint">{{ t("store.checkout.nameHint") }}</span>
      </label>

      <fieldset class="choice">
        <legend>{{ t("store.checkout.fulfillment") }}</legend>
        <label class="option">
          <input v-model="form.fulfillment" type="radio" name="fulfillment" value="pickup" />
          <span><b>{{ t("store.checkout.pickup") }}</b><span class="hint">{{ t("store.checkout.pickupHint") }}</span></span>
        </label>
        <label class="option">
          <input v-model="form.fulfillment" type="radio" name="fulfillment" value="delivery" :disabled="zones.length === 0" />
          <span>
            <b>{{ t("store.checkout.delivery") }}</b>
            <span class="hint">{{ zones.length ? t("store.checkout.deliveryHint") : t("store.checkout.noZones") }}</span>
          </span>
        </label>
        <span v-if="errors.fulfillment" class="error">{{ errors.fulfillment }}</span>
      </fieldset>

      <label v-if="form.fulfillment === 'delivery'" class="field">
        <span>{{ t("store.checkout.zone") }}</span>
        <select v-model="form.zoneId" name="delivery_zone_id" :aria-invalid="Boolean(errors.delivery_zone_id)">
          <option value="">{{ t("store.checkout.chooseZone") }}</option>
          <option v-for="option in zones" :key="option.id" :value="option.id">
            {{ t("store.checkout.zoneOption", { name: localized(option.name, option.name_en), fee: formatMoney(option.fee) }) }}
          </option>
        </select>
        <span v-if="errors.delivery_zone_id" class="error">{{ errors.delivery_zone_id }}</span>
      </label>

      <label class="field">
        <span>{{ t("store.checkout.occasion") }} {{ t("store.product.optional") }}</span>
        <input v-model="form.occasion" type="date" name="occasion_date" :min="today" :aria-invalid="Boolean(errors.occasion_date)" />
        <span v-if="errors.occasion_date" class="error">{{ errors.occasion_date }}</span>
        <span v-else class="hint">{{ t("store.checkout.occasionHint") }}</span>
      </label>

      <label class="field">
        <span>{{ t("store.checkout.notes") }} {{ t("store.product.optional") }}</span>
        <textarea v-model="form.notes" name="notes" rows="3" :maxlength="NOTES_LENGTH" :aria-invalid="Boolean(errors.notes)"></textarea>
        <span v-if="errors.notes" class="error">{{ errors.notes }}</span>
      </label>

      <label class="field">
        <span>{{ t("store.checkout.source") }} {{ t("store.product.optional") }}</span>
        <select v-model="form.source" name="source">
          <option value="">{{ t("store.checkout.sourceNone") }}</option>
          <option v-for="source in SOURCES" :key="source" :value="source">{{ t(`store.checkout.sources.${source}`) }}</option>
        </select>
      </label>

      <LiveNotice :message="notice" />
      <div class="form-actions">
        <button type="submit" class="btn primary" :disabled="sending">{{ sending ? t("store.checkout.submitting") : t("store.checkout.submit") }}</button>
        <RouterLink class="btn" :to="{ name: 'cart' }">{{ t("store.checkout.back") }}</RouterLink>
      </div>
    </form>

    <section class="panel summary" aria-labelledby="summary-title">
      <h2 id="summary-title">{{ t("store.checkout.summary") }}</h2>
      <ul class="lines">
        <li v-for="item in view.items" :key="item.id">
          <span>{{ localized(item.name, item.name_en) }} <span class="muted num">× {{ item.quantity }}</span></span>
          <span class="num">{{ formatMoney(item.line_total) }}</span>
        </li>
      </ul>
      <dl class="sums">
        <div><dt>{{ t("store.cart.subtotal") }}</dt><dd class="num">{{ formatMoney(view.subtotal) }}</dd></div>
        <div v-if="fee > 0"><dt>{{ t("store.cart.deliveryFee") }}</dt><dd class="num">{{ formatMoney(fee) }}</dd></div>
        <div class="grand"><dt>{{ t("store.cart.total") }}</dt><dd class="num">{{ formatMoney(total) }}</dd></div>
      </dl>
      <p class="ready">{{ readyOn ? t("store.checkout.earliest", { date: formatDay(readyOn) }) : t("store.cart.noCapacity") }}</p>
      <p v-if="view.needs_review" class="hint">{{ t("store.cart.needsReview") }}</p>
    </section>
  </div>
</template>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 20px; align-items: start; }
.form { display: flex; flex-direction: column; gap: 16px; }
.choice { margin: 0; padding: 0; border: 0; min-inline-size: 0; display: flex; flex-direction: column; gap: 8px; }
.choice legend { padding: 0; margin-block-end: 6px; font-size: 14px; color: var(--muted); }
.option { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--radius); cursor: pointer; }
.option:has(input:checked) { border-color: var(--accent); background: var(--brand-soft); }
.option:has(input:disabled) { cursor: not-allowed; opacity: 0.7; }
.option input { inline-size: 20px; min-block-size: 20px; margin-block-start: 4px; accent-color: var(--accent); flex: none; }
.option span { display: flex; flex-direction: column; }
.error { color: var(--risk); font-size: 14px; }
textarea { min-block-size: 88px; padding-block: 10px; resize: vertical; }
.summary { display: flex; flex-direction: column; gap: 10px; }
.summary h2 { margin: 0; font-size: 20px; }
.summary p { margin: 0; }
.lines { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.lines li { display: flex; justify-content: space-between; gap: 12px; }
.sums { margin: 0; display: grid; gap: 4px; padding-block-start: 10px; border-block-start: 1px dashed var(--line); }
.sums div { display: flex; justify-content: space-between; gap: 12px; }
.sums dd { margin: 0; }
.sums .grand { font-weight: 700; font-size: 18px; }
.ready { font-weight: 600; }
.back { margin-block-start: 16px; }
.done { display: flex; flex-direction: column; gap: 12px; max-inline-size: 620px; }
.done p { margin: 0; }
.done .amount { font-size: 20px; font-weight: 700; }
.done .pay { align-self: flex-start; }
.done .track { display: flex; flex-direction: column; gap: 8px; margin-block-start: 8px; padding-block-start: 16px; border-block-start: 1px dashed var(--line); }
.done .form-actions { margin-block-start: 0; }
@media (max-width: 860px) { .layout { grid-template-columns: 1fr; } }
</style>
