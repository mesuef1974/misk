<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { errorMessage } from "@/api/client";
import OrderItemEditor from "@/components/OrderItemEditor.vue";
import { formatMoney } from "@/domain/orders";
import { buildDraft, estimateTotal, newItem, type FormErrors, type OrderForm } from "@/domain/orderForm";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";

const router = useRouter();
const catalog = useCatalogStore();
const orders = useOrdersStore();

// مفتاح واحد لعمر النموذج: إعادة الإرسال بعد انقطاع لا تنشئ طلبًا ثانيًا.
const clientRef = crypto.randomUUID();
let nextKey = 1;

const form = reactive<OrderForm>({ customerName: "", occasionDate: "", notes: "", items: [newItem(nextKey++)] });
const errors = ref<FormErrors>({ items: {} });
const submitError = ref("");
const submitting = ref(false);

const estimate = computed(() => formatMoney(estimateTotal(form.items, catalog.templates)));
const catalogEmpty = computed(
  () => catalog.loaded && (catalog.templates.length === 0 || catalog.materials.length === 0),
);

onMounted(() => catalog.ensureLoaded());

function addItem(): void {
  form.items.push(newItem(nextKey++));
}

function removeItem(index: number): void {
  form.items.splice(index, 1);
}

async function submit(): Promise<void> {
  submitError.value = "";
  const result = buildDraft(form, clientRef, catalog.templates);
  errors.value = result.errors;
  if (!result.draft) {
    submitError.value = "صحّح الحقول المعلَّمة ثم أعد الحفظ";
    return;
  }
  submitting.value = true;
  try {
    const order = await orders.create(result.draft);
    await router.push({ name: "order-detail", params: { id: order.id } });
  } catch (error) {
    submitError.value = errorMessage(error);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="page-head">
    <h1>طلب جديد</h1>
    <RouterLink class="btn" :to="{ name: 'orders' }">رجوع للطلبات</RouterLink>
  </div>

  <div v-if="catalog.loadError" class="notice" role="alert">
    {{ catalog.loadError }}
    <button type="button" class="btn retry" @click="catalog.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="!catalog.loaded" class="muted" role="status">يحمّل القوالب والمواد…</p>
  <p v-else-if="catalogEmpty" class="panel muted">
    لا يمكن إنشاء طلب قبل تعريف قالب واحد ومادة واحدة على الأقل في الكتالوج.
  </p>

  <form v-else novalidate @submit.prevent="submit">
    <section class="panel customer">
      <label class="field">
        <span>اسم العميل</span>
        <input
          v-model="form.customerName"
          type="text"
          maxlength="120"
          autocomplete="off"
          :aria-invalid="Boolean(errors.customerName)"
        />
        <span v-if="errors.customerName" class="error">{{ errors.customerName }}</span>
      </label>
      <label class="field">
        <span>تاريخ المناسبة (اختياري)</span>
        <input v-model="form.occasionDate" type="date" />
      </label>
      <label class="field notes">
        <span>ملاحظات (اختياري)</span>
        <textarea v-model="form.notes" rows="2"></textarea>
      </label>
    </section>

    <OrderItemEditor
      v-for="(item, index) in form.items"
      :key="item.key"
      :item="item"
      :index="index"
      :templates="catalog.templates"
      :materials="catalog.materials"
      :errors="errors.items[item.key]"
      :removable="form.items.length > 1"
      @patch="Object.assign(item, $event)"
      @param="(name, value) => (item.params[name] = value)"
      @remove="removeItem(index)"
    />

    <button type="button" class="btn" @click="addItem">إضافة بند</button>

    <div v-if="submitError" class="notice" role="alert">{{ submitError }}</div>

    <div class="footer">
      <span class="estimate">المجموع التقديري: <strong>{{ estimate }}</strong></span>
      <button type="submit" class="btn primary" :disabled="submitting">
        {{ submitting ? "يحفظ…" : "حفظ الطلب مسودةً" }}
      </button>
    </div>
  </form>
</template>

<style scoped>
form { display: grid; gap: 16px; justify-items: start; }
form > * { inline-size: 100%; }
form > .btn { inline-size: auto; }
.customer { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 16px; }
.notes { grid-column: 1 / -1; }
.retry { margin-inline-start: 12px; }
.footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.estimate strong { font-variant-numeric: tabular-nums; }
</style>
