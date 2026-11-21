<script setup lang="ts">
// صفحة مزوّد الاختبار (PAYMENT_PROVIDER=test): تقوم مقام صفحة البوابة المستضافة حتى تُختار البوابة (الطلب 9).
// لا مال فيها: المشرف يحاكي إشعار البوابة، والخادم يعالجه بالمسار نفسه الذي يعالج به إشعارًا حقيقيًّا.
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import LiveNotice from "@/components/LiveNotice.vue";
import { storeError } from "@/domain/store";
import { storeService } from "@/services/store";
import { useCartStore } from "@/stores/cart";
import { useSessionStore } from "@/stores/session";

const props = defineProps<{ sessionId: string }>();
const { t } = useI18n();
const session = useSessionStore();
const cart = useCartStore();

const working = ref(false);
const outcome = ref("");
const failure = ref("");

onMounted(() => session.ensureChecked());

async function simulate(result: "captured" | "failed"): Promise<void> {
  working.value = true;
  outcome.value = "";
  failure.value = "";
  try {
    const answer = await storeService.simulatePayment(props.sessionId, result);
    outcome.value = t("store.testPay.outcome", { outcome: answer.outcome });
    void cart.load();
  } catch (error) {
    failure.value = storeError(error, t("errors.unexpected")).message;
  } finally {
    working.value = false;
  }
}
</script>

<template>
  <h1>{{ t("store.testPay.heading") }}</h1>
  <p class="lead">{{ t("store.testPay.lead") }}</p>

  <section class="panel box">
    <template v-if="session.isStaff">
      <div class="form-actions">
        <button type="button" class="btn primary" :disabled="working" @click="simulate('captured')">{{ t("store.testPay.capture") }}</button>
        <button type="button" class="btn danger" :disabled="working" @click="simulate('failed')">{{ t("store.testPay.fail") }}</button>
      </div>
      <p v-if="working" class="hint">{{ t("store.testPay.working") }}</p>
    </template>
    <template v-else-if="session.checked">
      <p>{{ t("store.testPay.staffOnly") }}</p>
      <RouterLink class="btn" :to="{ name: 'login', query: { next: $route.fullPath } }">{{ t("store.testPay.login") }}</RouterLink>
    </template>
    <LiveNotice kind="status" :message="outcome" />
    <LiveNotice :message="failure" />
    <RouterLink class="btn" :to="{ name: 'cart' }">{{ t("store.testPay.cart") }}</RouterLink>
  </section>
</template>

<style scoped>
.box { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; max-inline-size: 560px; }
.box p { margin: 0; }
.box .form-actions { margin-block-start: 0; }
</style>
