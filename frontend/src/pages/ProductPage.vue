<script setup lang="ts">
// صفحة المنتج والمصمِّم: الحقول من مخطط القالب، والمعاينة ملف القص نفسه من الخادم، والحدود من المعايرة.
// الخادم هو الحَكَم: فحص الواجهة يُظهر الخطأ بجانب الحقل، والمعاينة والإضافة تعيدان حكمه.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import LiveNotice from "@/components/LiveNotice.vue";
import { formatMoney, lineTotal } from "@/domain/orders";
import { choiceLabel, cleanParams, fieldLabel, type ParamField, type ParamValue, type ParamValues } from "@/domain/params";
import { initialParams, limitFor, localized, storeError, svgDataUrl, textLength } from "@/domain/store";
import { currentLocale } from "@/i18n";
import { storeService, type FieldLimit, type Preview, type StoreTemplateDetail } from "@/services/store";
import { useCartStore } from "@/stores/cart";
import { useStorefrontStore } from "@/stores/storefront";

const props = defineProps<{ slug: string }>();

const PREVIEW_DELAY_MS = 350;
const MAX_QUANTITY = 50; // نسخة الواجهة من MAX_LINE_QUANTITY في apps/checkout/cart.py

const { t, locale } = useI18n();
const router = useRouter();
const cart = useCartStore();
const storefront = useStorefrontStore();

const detail = ref<StoreTemplateDetail | null>(null);
const loadError = ref("");
const materialId = ref<number | "">("");
const params = ref<ParamValues>({});
const quantity = ref<number | "">(1);
const acknowledged = ref(false);
const limits = ref<FieldLimit[]>([]);

const preview = ref<Preview | null>(null);
const previewing = ref(false);
const errors = ref<Record<string, string>>({});
const notice = ref("");
const suggestions = ref<string[]>([]);
const adding = ref(false);

/** يزيد عند كل طلب معاينة وكل تحميل: ردّ طلب أقدم لا يكتب فوق الأحدث. */
let previewTicket = 0;
let loadTicket = 0;
let timer: ReturnType<typeof setTimeout> | undefined;

const name = computed(() => (detail.value ? localized(detail.value.name, detail.value.name_en) : ""));
const description = computed(() => (detail.value ? localized(detail.value.description, detail.value.description_en) : ""));
const total = computed(() => (detail.value && quantity.value !== "" ? lineTotal(quantity.value, detail.value.base_price) : 0));
const quantityOk = computed(() => Number.isInteger(quantity.value) && Number(quantity.value) >= 1 && Number(quantity.value) <= MAX_QUANTITY);
const canAdd = computed(() => Boolean(preview.value) && !previewing.value && acknowledged.value && quantityOk.value && !adding.value);
const suggested = computed(() =>
  suggestions.value.map((slug) => {
    const product = storefront.bySlug(slug);
    return { slug, name: product ? localized(product.name, product.name_en) : slug };
  }),
);

function clearPreview(): void {
  previewTicket += 1;
  clearTimeout(timer);
  preview.value = null;
  previewing.value = false;
}

async function load(): Promise<void> {
  const ticket = ++loadTicket;
  clearPreview();
  detail.value = null;
  loadError.value = "";
  errors.value = {};
  notice.value = "";
  suggestions.value = [];
  limits.value = [];
  acknowledged.value = false;
  quantity.value = 1;
  try {
    const loaded = await storeService.template(props.slug, currentLocale());
    if (ticket !== loadTicket) return;
    params.value = initialParams(loaded.fields);
    materialId.value = loaded.materials[0]?.id ?? "";
    detail.value = loaded;
  } catch (error) {
    if (ticket === loadTicket) loadError.value = storeError(error, t("errors.unexpected")).message;
  }
}

async function loadLimits(): Promise<void> {
  limits.value = [];
  if (materialId.value === "") return;
  const material = materialId.value;
  try {
    const loaded = await storeService.limits(props.slug, material, currentLocale());
    if (material === materialId.value) limits.value = loaded;
  } catch {
    // العدّاد تقديري ومساعد: غيابه لا يمنع التصميم، والحكم في المعاينة.
  }
}

function schedulePreview(): void {
  clearTimeout(timer);
  const ticket = ++previewTicket;
  if (!detail.value || materialId.value === "") {
    preview.value = null;
    previewing.value = false;
    return;
  }
  const cleaned = cleanParams(detail.value.fields, params.value);
  if (Object.keys(cleaned.errors).length > 0) {
    // حقل مطلوب لم يُملأ بعد: لا معاينة ولا خطأ قبل أن يحاول العميل الإضافة.
    preview.value = null;
    previewing.value = false;
    return;
  }
  previewing.value = true;
  const material = materialId.value;
  timer = setTimeout(() => void requestPreview(ticket, material, cleaned.params), PREVIEW_DELAY_MS);
}

async function requestPreview(ticket: number, material: number, cleaned: ParamValues): Promise<void> {
  try {
    const rendered = await storeService.preview(props.slug, material, cleaned, currentLocale());
    if (ticket !== previewTicket) return;
    preview.value = rendered;
    errors.value = {};
    notice.value = "";
    suggestions.value = [];
  } catch (error) {
    if (ticket !== previewTicket) return;
    preview.value = null;
    showError(error);
  } finally {
    if (ticket === previewTicket) previewing.value = false;
  }
}

function showError(error: unknown): void {
  const failure = storeError(error, t("errors.unexpected"));
  errors.value = failure.fields;
  notice.value = failure.message;
  suggestions.value = failure.suggestions;
  if (failure.suggestions.length > 0) void storefront.ensureLoaded();
}

function setParam(field: ParamField, value: ParamValue): void {
  params.value = { ...params.value, [field.name]: value };
}

/** قيمة الخيار تُقرأ من المخطط لا من نص <option>، فتبقى الخيارات الرقمية أرقامًا. */
function chooseParam(field: ParamField, event: Event): void {
  const offset = (field.required ?? true) ? 0 : 1;
  const index = (event.target as HTMLSelectElement).selectedIndex - offset;
  setParam(field, index >= 0 ? (field.choices ?? [])[index] : "");
}

function numberOf(event: Event): number | "" {
  const raw = (event.target as HTMLInputElement).value;
  return raw === "" ? "" : Number(raw);
}

function counter(field: ParamField): { count: number; max: number; over: boolean } | null {
  const limit = limitFor(limits.value, field.name, params.value);
  if (!limit) return null;
  const count = textLength(params.value[field.name]);
  return { count, max: limit.max_chars, over: count > limit.max_chars };
}

async function add(): Promise<void> {
  if (!detail.value || materialId.value === "" || quantity.value === "") return;
  const cleaned = cleanParams(detail.value.fields, params.value);
  if (Object.keys(cleaned.errors).length > 0 || !preview.value) {
    errors.value = cleaned.errors;
    notice.value = t("store.product.fixFirst");
    return;
  }
  adding.value = true;
  try {
    await cart.add({
      template_slug: detail.value.slug,
      material_id: materialId.value,
      params: cleaned.params,
      quantity: quantity.value,
      sha256: preview.value.sha256,
      acknowledged: acknowledged.value,
    });
    await router.push({ name: "cart" });
  } catch (error) {
    showError(error);
    // المعاينة تغيّرت في الخادم منذ أقرّها العميل: تُرسم من جديد ليقرّها ثانيةً.
    if (storeError(error, "").code === "preview_mismatch") {
      acknowledged.value = false;
      schedulePreview();
    }
  } finally {
    adding.value = false;
  }
}

watch(() => props.slug, load, { immediate: true });
// رسائل الخادم بلغة الطلب: تبديل اللغة يعيد التحميل لتعود بلغة الصفحة.
watch(locale, load);
watch(materialId, () => void loadLimits());
watch(
  [materialId, params],
  () => {
    // الإقرار يخصّ النص الذي رآه العميل: أي تغيير يُسقطه.
    acknowledged.value = false;
    schedulePreview();
  },
  { deep: true },
);
onBeforeUnmount(clearPreview);
</script>

<template>
  <div class="page-head">
    <h1>{{ name || t("store.product.loading") }}</h1>
    <RouterLink class="btn" :to="{ name: 'products' }">{{ t("store.product.back") }}</RouterLink>
  </div>

  <div v-if="loadError" class="notice" role="alert">{{ loadError }}</div>

  <template v-else-if="detail">
    <p v-if="description" class="lead">{{ description }}</p>

    <div v-if="detail.materials.length === 0" class="notice" role="alert">{{ t("store.product.unavailable") }}</div>

    <div v-else class="designer">
      <form class="panel fields" novalidate @submit.prevent="add">
        <label class="field">
          <span>{{ t("store.product.material") }}</span>
          <select v-model.number="materialId" name="material">
            <option v-for="material in detail.materials" :key="material.id" :value="material.id">
              {{ t("store.product.materialOption", { name: localized(material.name, material.name_en), thickness: Number(material.thickness_mm) }) }}
            </option>
          </select>
        </label>

        <template v-for="field in detail.fields" :key="field.name">
          <label v-if="field.type === 'bool'" class="check">
            <input
              type="checkbox"
              :name="field.name"
              :checked="params[field.name] === true"
              @change="setParam(field, ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ fieldLabel(field) }}</span>
          </label>

          <label v-else class="field">
            <span>{{ fieldLabel(field) }}<template v-if="field.required === false"> {{ t("store.product.optional") }}</template></span>
            <select
              v-if="field.type === 'choice'"
              :name="field.name"
              :aria-invalid="Boolean(errors[field.name])"
              @change="chooseParam(field, $event)"
            >
              <option v-if="field.required === false" value="" :selected="params[field.name] === ''">{{ t("store.product.choose") }}</option>
              <option v-for="choice in field.choices" :key="String(choice)" :selected="params[field.name] === choice">
                {{ choiceLabel(field, choice) }}
              </option>
            </select>
            <input
              v-else-if="field.type === 'int'"
              type="number"
              step="1"
              inputmode="numeric"
              :name="field.name"
              :min="field.min"
              :max="field.max"
              :value="params[field.name]"
              :aria-invalid="Boolean(errors[field.name])"
              @input="setParam(field, numberOf($event))"
            />
            <input
              v-else
              type="text"
              dir="auto"
              autocomplete="off"
              :name="field.name"
              :maxlength="field.max_length"
              :value="params[field.name]"
              :aria-invalid="Boolean(errors[field.name])"
              @input="setParam(field, ($event.target as HTMLInputElement).value)"
            />
            <span v-if="field.type === 'text' && counter(field)" class="hint num" :class="{ over: counter(field)?.over }">
              {{ t("store.product.counter", { count: counter(field)?.count, max: counter(field)?.max }) }}
            </span>
            <span v-if="errors[field.name]" class="error">{{ errors[field.name] }}</span>
          </label>
        </template>

        <label class="field quantity">
          <span>{{ t("store.product.quantity") }}</span>
          <input v-model.number="quantity" type="number" name="quantity" min="1" :max="MAX_QUANTITY" step="1" inputmode="numeric" :aria-invalid="!quantityOk" />
        </label>

        <dl class="sums">
          <div><dt>{{ t("store.product.unitPrice") }}</dt><dd class="num">{{ formatMoney(detail.base_price) }}</dd></div>
          <div class="grand"><dt>{{ t("store.product.total") }}</dt><dd class="num">{{ formatMoney(total) }}</dd></div>
        </dl>

        <LiveNotice :message="notice" />
        <div v-if="suggested.length" class="suggest">
          <span>{{ t("store.product.suggestions") }}</span>
          <RouterLink v-for="item in suggested" :key="item.slug" class="chip" :to="{ name: 'product', params: { slug: item.slug } }">{{ item.name }}</RouterLink>
        </div>

        <label class="check ack">
          <input v-model="acknowledged" type="checkbox" name="acknowledged" :disabled="!preview || previewing" />
          <span>{{ t("store.product.acknowledge") }}</span>
        </label>
        <button type="submit" class="btn primary" :disabled="!canAdd">{{ adding ? t("store.product.adding") : t("store.product.add") }}</button>
      </form>

      <section class="panel stage" aria-labelledby="preview-title">
        <h2 id="preview-title">{{ t("store.product.preview") }}</h2>
        <div class="canvas" :class="{ busy: previewing }">
          <img v-if="preview" :src="svgDataUrl(preview.svg)" :alt="t('store.product.previewAlt', { name })" />
          <p v-else class="muted">{{ previewing ? t("store.product.previewUpdating") : t("store.product.previewEmpty") }}</p>
        </div>
        <template v-if="preview">
          <p class="hint num">{{ t("store.product.pieceSize", { width: preview.width_mm, height: preview.height_mm }) }}</p>
          <p class="hint">{{ t("store.product.previewNote") }}</p>
          <p v-if="preview.needs_review" class="notice ok">{{ t("store.product.needsReview") }}</p>
        </template>
      </section>
    </div>
  </template>
</template>

<style scoped>
.designer { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr); gap: 20px; align-items: start; }
.fields { display: flex; flex-direction: column; gap: 14px; }
.quantity { max-inline-size: 160px; }
.hint.over, .error { color: var(--risk); }
.sums { margin: 0; display: grid; gap: 4px; padding-block-start: 12px; border-block-start: 1px dashed var(--line); }
.sums div { display: flex; justify-content: space-between; gap: 12px; }
.sums dd { margin: 0; }
.sums .grand { font-weight: 700; font-size: 18px; }
.suggest { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 14px; }
.suggest .chip { display: inline-flex; align-items: center; text-decoration: none; }
.ack { align-items: flex-start; }
.ack input { margin-block-start: 4px; }
.stage { position: sticky; inset-block-start: 20px; display: flex; flex-direction: column; gap: 10px; }
.stage h2 { margin: 0; font-size: 20px; }
.stage p { margin: 0; }
/* المعاينة على سطح نهاري في الوضعين: ألوان ملف القص (أسود للحفر، أحمر للقص) تُقرأ عليه كما تُقرأ في الورشة. */
.canvas {
  display: grid; place-items: center; min-block-size: 260px; padding: 16px;
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--day-surface);
}
.canvas.busy { opacity: 0.6; }
.canvas img { display: block; max-inline-size: 100%; max-block-size: 420px; inline-size: 100%; object-fit: contain; }
.canvas .muted { color: var(--print-muted); }
@media (max-width: 860px) {
  .designer { grid-template-columns: 1fr; }
  .stage { position: static; order: -1; }
}
</style>
