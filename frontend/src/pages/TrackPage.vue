<script setup lang="ts">
// تتبّع الطلب بالرابط السري: الحالة وخطواتها والمحتويات، وحجز موعد الاستلام حين يجهز. بلا حساب ولا بيان شخصي.
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ApiError } from "@/api/client";
import LiveNotice from "@/components/LiveNotice.vue";
import { formatMoney } from "@/domain/orders";
import { formatDay, formatMoment, formatTime, localized, storeError } from "@/domain/store";
import { currentLocale } from "@/i18n";
import { storeService, type PickupSlots, type Tracking } from "@/services/store";

const props = defineProps<{ token: string }>();
const { t, locale } = useI18n();

const order = ref<Tracking | null>(null);
const loading = ref(false);
const missing = ref(false);
const loadError = ref("");
const slots = ref<PickupSlots | null>(null);
const choosing = ref(false);
const booking = ref("");
const notice = ref("");
let ticket = 0;

async function loadSlots(): Promise<void> {
  slots.value = null;
  if (!order.value?.can_book_pickup) return;
  try {
    slots.value = await storeService.pickupSlots(props.token, currentLocale());
  } catch (error) {
    notice.value = storeError(error, t("errors.unexpected")).message;
  }
}

async function load(): Promise<void> {
  const mine = ++ticket;
  loading.value = true;
  loadError.value = "";
  missing.value = false;
  notice.value = "";
  try {
    const loaded = await storeService.track(props.token, currentLocale());
    if (mine !== ticket) return;
    order.value = loaded;
    // من لم يحجز بعد يرى المواعيد مباشرةً؛ من حجز يفتحها بزر «تغيير الموعد».
    choosing.value = loaded.can_book_pickup && !loaded.pickup;
    if (choosing.value) await loadSlots();
  } catch (error) {
    if (mine !== ticket) return;
    order.value = null;
    if (error instanceof ApiError && error.status === 404) missing.value = true;
    else loadError.value = storeError(error, t("errors.unexpected")).message;
  } finally {
    if (mine === ticket) loading.value = false;
  }
}

async function openSlots(): Promise<void> {
  choosing.value = true;
  await loadSlots();
}

async function book(startsAt: string): Promise<void> {
  booking.value = startsAt;
  notice.value = "";
  try {
    order.value = await storeService.bookPickup(props.token, startsAt, currentLocale());
    choosing.value = false;
    slots.value = null;
  } catch (error) {
    notice.value = storeError(error, t("errors.unexpected")).message;
    // الموعد سُبق إليه أو لم يعد متاحًا: تُعرض المواعيد كما صارت.
    await loadSlots();
  } finally {
    booking.value = "";
  }
}

// تسميات الحالات يرسلها الخادم بلغة الطلب: تبديل اللغة يعيد التحميل.
watch([() => props.token, locale], load, { immediate: true });
</script>

<template>
  <div class="page-head">
    <h1>{{ t("store.track.heading") }}</h1>
    <button type="button" class="btn" :disabled="loading" @click="load">{{ t("store.track.refresh") }}</button>
  </div>

  <div v-if="missing" class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ t("store.track.notFound") }}</p>
    </div>
  </div>
  <div v-else-if="loadError" class="notice" role="alert">{{ loadError }}</div>
  <p v-else-if="!order" class="muted">{{ t("store.track.loading") }}</p>

  <template v-else>
    <section class="panel state">
      <p class="now"><span class="pill">{{ order.status_label }}</span></p>
      <p class="hint">{{ t("store.track.updated", { time: formatMoment(order.updated_at) }) }}</p>
      <p v-if="order.occasion_date">{{ t("store.track.occasion", { date: formatDay(order.occasion_date) }) }}</p>
      <p v-if="order.delivery_zone">{{ t("store.track.deliveryZone", { zone: localized(order.delivery_zone.name, order.delivery_zone.name_en) }) }}</p>
    </section>

    <section aria-labelledby="track-steps">
      <h2 id="track-steps">{{ t("store.track.steps") }}</h2>
      <ol class="steps">
        <li v-for="step in order.steps" :key="step.status" :class="{ reached: step.reached, current: step.status === order.status }" :aria-current="step.status === order.status ? 'step' : undefined">
          <span class="dot" aria-hidden="true"></span>
          <span class="label">
            <b>{{ step.label }}</b>
            <span class="hint">{{ step.at ? formatMoment(step.at) : step.reached ? t("store.track.reached") : t("store.track.pending") }}</span>
          </span>
        </li>
      </ol>
    </section>

    <section v-if="order.fulfillment === 'pickup'" class="panel pickup" aria-labelledby="track-pickup">
      <h2 id="track-pickup">{{ t("store.track.pickup.heading") }}</h2>
      <template v-if="order.pickup">
        <p class="booked">{{ t("store.track.pickup.booked", { time: formatMoment(order.pickup.starts_at) }) }}</p>
        <p class="hint">{{ t("store.track.pickup.address") }}</p>
      </template>
      <p v-else-if="!order.can_book_pickup" class="hint">{{ t("store.track.pickup.later") }}</p>

      <button v-if="order.can_book_pickup && order.pickup && !choosing" type="button" class="btn" @click="openSlots">
        {{ t("store.track.pickup.change") }}
      </button>

      <template v-if="choosing && slots">
        <p v-if="slots.days.length === 0" class="hint">{{ t("store.track.pickup.none") }}</p>
        <template v-else>
          <p class="hint">{{ t("store.track.pickup.choose") }} — {{ t("store.track.pickup.slotLength", { minutes: slots.slot_min }) }}</p>
          <div v-for="day in slots.days" :key="day.day" class="day">
            <h3>{{ formatDay(day.day) }}</h3>
            <div class="filters">
              <button
                v-for="slot in day.slots"
                :key="slot"
                type="button"
                class="chip num"
                :disabled="booking !== ''"
                :aria-label="t('store.track.pickup.book', { time: formatMoment(slot) })"
                @click="book(slot)"
              >
                {{ booking === slot ? t("store.track.pickup.booking") : formatTime(slot) }}
              </button>
            </div>
          </div>
        </template>
      </template>
      <LiveNotice :message="notice" />
    </section>

    <section class="panel" aria-labelledby="track-items">
      <h2 id="track-items">{{ t("store.track.items") }}</h2>
      <ul class="lines">
        <li v-for="(item, index) in order.items" :key="index">
          <span>
            {{ t("store.track.itemLine", { name: localized(item.name, item.name_en), material: localized(item.material_name, item.material_name_en) }) }}
            <span class="muted num">× {{ item.quantity }}</span>
          </span>
          <span class="num">{{ formatMoney(item.line_total) }}</span>
        </li>
      </ul>
      <dl class="sums">
        <div><dt>{{ t("store.track.subtotal") }}</dt><dd class="num">{{ formatMoney(order.subtotal) }}</dd></div>
        <div v-if="Number(order.delivery_fee) > 0"><dt>{{ t("store.track.deliveryFee") }}</dt><dd class="num">{{ formatMoney(order.delivery_fee) }}</dd></div>
        <div class="grand"><dt>{{ t("store.track.total") }}</dt><dd class="num">{{ formatMoney(order.total) }}</dd></div>
      </dl>
    </section>
  </template>
</template>

<style scoped>
h2 { font-size: 20px; margin-block: 0 12px; }
h3 { font-size: 16px; margin-block: 12px 8px; }
.panel p { margin: 0; }
.state { display: flex; flex-direction: column; gap: 6px; }
.now .pill { font-size: 16px; padding: 4px 14px; }
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
.steps li { display: flex; gap: 12px; padding-block: 8px; color: var(--muted); }
.steps .dot { inline-size: 14px; block-size: 14px; margin-block-start: 6px; border-radius: 50%; border: 2px solid var(--line-strong); flex: none; }
.steps .reached { color: var(--ink); }
.steps .reached .dot { background: var(--accent); border-color: var(--accent); }
.steps .current b { color: var(--accent); }
.steps .label { display: flex; flex-direction: column; line-height: 1.5; }
.pickup { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.pickup .booked { font-weight: 700; font-size: 18px; }
.pickup .day { inline-size: 100%; }
.lines { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.lines li { display: flex; justify-content: space-between; gap: 12px; }
.sums { margin: 12px 0 0; display: grid; gap: 4px; padding-block-start: 10px; border-block-start: 1px dashed var(--line); }
.sums div { display: flex; justify-content: space-between; gap: 12px; }
.sums dd { margin: 0; }
.sums .grand { font-weight: 700; font-size: 18px; }
</style>
