<script setup lang="ts">
// صفحة تصميم جاهز: صور العرض والمقاس، واختيار النسخة والخامة ثم الإضافة إلى السلة. لا معاينة ولا تعديل:
// العميل يقرّ بالمقاس والخامة. الأسعار من الخادم كما هي، وملف التصميم لا يصل المتصفح.
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import LiveNotice from "@/components/LiveNotice.vue";
import { materialName } from "@/domain/catalog";
import { formatMoney } from "@/domain/orders";
import { cleanParams, fieldLabel, type ParamField, type ParamValues } from "@/domain/params";
import { initialParams, localized, storeError, textLength } from "@/domain/store";
import { currentLocale } from "@/i18n";
import { storeService, type StoreDesignDetail } from "@/services/store";
import { useCartStore } from "@/stores/cart";

const MAX_QUANTITY = 50; // نسخة الواجهة من MAX_LINE_QUANTITY في apps/checkout/cart.py

const props = defineProps<{ slug: string }>();
const { t, locale } = useI18n();
const router = useRouter();
const cart = useCartStore();

const detail = ref<StoreDesignDetail | null>(null);
const loadError = ref("");
const shown = ref(0);
const choice = ref(""); // مفتاح العرض المختار: رمز النسخة ثم معرّف الخامة
const quantity = ref<number | "">(1);
const acknowledged = ref(false);
const params = ref<ParamValues>({});
const fieldErrors = ref<Record<string, string>>({});
const adding = ref(false);
const notice = ref("");
let ticket = 0;

const offerKey = (code: string, materialId: number) => `${code}|${materialId}`;
const offers = computed(() =>
  (detail.value?.variants ?? []).flatMap((variant) => variant.offers.map((offer) => ({ variant, offer }))),
);
const chosen = computed(
  () => offers.value.find((row) => offerKey(row.variant.code, row.offer.material.id) === choice.value) ?? null,
);
const quantityOk = computed(
  () => typeof quantity.value === "number" && Number.isInteger(quantity.value) && quantity.value >= 1 && quantity.value <= MAX_QUANTITY,
);
const total = computed(() =>
  chosen.value && quantityOk.value ? Number(chosen.value.offer.price) * Number(quantity.value) : null,
);
// حقول التخصيص نصوص فقط (الخادم يفرضه عند الاعتماد)؛ والحكم القاطع للخادم بعد سياسة النص.
const textFields = computed(() => (detail.value?.fields ?? []).filter((field) => field.type === "text"));
const cleaned = computed(() => cleanParams(textFields.value, params.value));
const paramsOk = computed(() => Object.keys(cleaned.value.errors).length === 0);
const canAdd = computed(
  () => Boolean(chosen.value) && quantityOk.value && paramsOk.value && acknowledged.value && !adding.value && !cart.locked,
);

const maxLength = (field: ParamField) => field.max_length ?? 200; // DEFAULT_TEXT_LENGTH في apps/catalog/domain.py
const countOf = (field: ParamField) => textLength(params.value[field.name]);
const errorOf = (field: ParamField) =>
  fieldErrors.value[field.name] || (countOf(field) > maxLength(field) ? cleaned.value.errors[field.name] : "");
function setText(field: ParamField, value: string): void {
  params.value = { ...params.value, [field.name]: value };
  fieldErrors.value = {};
}

const number = (value: string) => String(Number(value));

const name = computed(() => (detail.value ? localized(detail.value.name, detail.value.name_en) : ""));
const description = computed(() =>
  detail.value ? localized(detail.value.description, detail.value.description_en) : "",
);
const size = computed(() => {
  const design = detail.value;
  if (!design?.assembled_width_mm || !design.assembled_height_mm) return "";
  const named = { width: number(design.assembled_width_mm), height: number(design.assembled_height_mm) };
  return design.assembled_depth_mm
    ? t("store.design.sizeValueDeep", { ...named, depth: number(design.assembled_depth_mm) })
    : t("store.design.sizeValue", named);
});
// مقاس النسخة المباعة (قياس القطعة المقصوصة): يظهر لكل نسخة حتى لو لم يُدخَل مقاس التركيب للتصميم.
const variantSize = (variant: { sheet_width_mm: string | null; sheet_height_mm: string | null }) =>
  variant.sheet_width_mm && variant.sheet_height_mm
    ? t("store.design.sizeValue", { width: number(variant.sheet_width_mm), height: number(variant.sheet_height_mm) })
    : "";
const image = computed(() => detail.value?.images[shown.value] ?? null);

async function load(): Promise<void> {
  const mine = ++ticket;
  loadError.value = "";
  detail.value = null;
  shown.value = 0;
  fieldErrors.value = {};
  try {
    const result = await storeService.design(props.slug, currentLocale());
    if (mine !== ticket) return;
    detail.value = result;
    params.value = initialParams(result.fields);
    // عرض واحد لا اختيار فيه؛ والاختيار السابق يبقى إن بقي معروضًا بعد إعادة التحميل.
    if (offers.value.length === 1) choice.value = offerKey(offers.value[0].variant.code, offers.value[0].offer.material.id);
    else if (!chosen.value) choice.value = "";
  } catch (error) {
    if (mine === ticket) loadError.value = storeError(error, t("errors.unexpected")).message;
  }
}

async function add(): Promise<void> {
  if (!detail.value || !chosen.value || !quantityOk.value) return;
  adding.value = true;
  notice.value = "";
  try {
    await cart.addDesign({
      design_slug: detail.value.slug,
      variant_code: chosen.value.variant.code,
      material_id: chosen.value.offer.material.id,
      quantity: Number(quantity.value),
      acknowledged: acknowledged.value,
      params: cleaned.value.params,
    });
    await router.push({ name: "cart" });
  } catch (error) {
    const failure = storeError(error, t("errors.unexpected"));
    notice.value = failure.message;
    fieldErrors.value = failure.fields;
    // السعر أو العرض تغيّر في الخادم: تُعاد الصفحة بما يُباع الآن ليقرّه العميل ثانيةً.
    if (failure.code === "not_for_sale") {
      acknowledged.value = false;
      await load();
    }
  } finally {
    adding.value = false;
  }
}

onMounted(() => cart.ensureLoaded());
watch(() => props.slug, load, { immediate: true });
// الإقرار يخصّ النسخة والخامة المختارتين: تغييرهما يُسقطه.
watch(choice, () => (acknowledged.value = false));
// ونص التخصيص يُقرّ كما كُتب: تغييره يُسقط الإقرار.
watch(params, () => (acknowledged.value = false));
// رسالة «غير موجود» من الخادم بلغة الطلب: تُعاد عند تبديل اللغة.
watch(locale, () => loadError.value && load());
</script>

<template>
  <div class="page-head">
    <h1>{{ name || (loadError ? t("store.designs.heading") : t("store.design.loading")) }}</h1>
    <RouterLink class="btn" :to="{ name: 'designs' }">{{ t("store.design.back") }}</RouterLink>
  </div>

  <div v-if="loadError" class="notice" role="alert">{{ loadError }}</div>

  <div v-else-if="detail" class="design">
    <section class="gallery">
      <div class="shot">
        <img v-if="image" :src="`${image.url}?w=960`" :alt="localized(image.alt, image.alt_en)" />
      </div>
      <ul v-if="detail.images.length > 1" class="thumbs">
        <li v-for="(item, index) in detail.images" :key="item.url">
          <button type="button" :class="{ active: index === shown }" :aria-pressed="index === shown" @click="shown = index">
            <img :src="`${item.url}?w=480`" :alt="localized(item.alt, item.alt_en)" loading="lazy" />
          </button>
        </li>
      </ul>
    </section>

    <section class="panel info">
      <p v-if="description" class="about">{{ description }}</p>
      <dl v-if="size" class="facts">
        <div><dt>{{ t("store.design.size") }}</dt><dd class="num">{{ size }}</dd></div>
      </dl>

      <form class="order" novalidate @submit.prevent="add">
        <h2 id="options-title">{{ t("store.design.options") }}</h2>
        <div role="radiogroup" aria-labelledby="options-title" class="variants">
          <div v-for="variant in detail.variants" :key="variant.code" class="variant">
            <h3 v-if="detail.variants.length > 1 && variant.code">{{ t("store.design.variant", { code: variant.code }) }}</h3>
            <p v-if="variantSize(variant)" class="hint num">{{ t("store.design.size") }}: {{ variantSize(variant) }}</p>
            <ul class="offers">
              <li v-for="offer in variant.offers" :key="offer.material.id">
                <label class="check">
                  <input v-model="choice" type="radio" name="offer" :value="offerKey(variant.code, offer.material.id)" />
                  <span>{{ t("store.design.material", { name: materialName(offer.material), thickness: number(offer.material.thickness_mm) }) }}</span>
                </label>
                <b class="num">{{ formatMoney(offer.price) }}</b>
              </li>
            </ul>
          </div>
        </div>

        <fieldset v-if="textFields.length" class="personalize">
          <legend>{{ t("store.design.personalize") }}</legend>
          <label v-for="field in textFields" :key="field.name" class="field">
            <span>{{ fieldLabel(field) }}<template v-if="field.required === false"> {{ t("store.design.optional") }}</template></span>
            <input
              type="text"
              dir="auto"
              autocomplete="off"
              :name="field.name"
              :maxlength="maxLength(field)"
              :value="params[field.name]"
              :aria-invalid="Boolean(errorOf(field))"
              @input="setText(field, ($event.target as HTMLInputElement).value)"
            />
            <span class="hint num">{{ t("store.design.counter", { count: countOf(field), max: maxLength(field) }) }}</span>
            <span v-if="errorOf(field)" class="error">{{ errorOf(field) }}</span>
          </label>
          <p class="hint">{{ t("store.design.personalizeNote") }}</p>
        </fieldset>

        <label class="qty">
          <span>{{ t("store.design.quantity") }}</span>
          <input v-model.number="quantity" type="number" name="quantity" min="1" :max="MAX_QUANTITY" inputmode="numeric" class="num" />
        </label>

        <dl v-if="chosen" class="sums">
          <div><dt>{{ t("store.design.unitPrice") }}</dt><dd class="num">{{ formatMoney(chosen.offer.price) }}</dd></div>
          <div v-if="total !== null" class="grand"><dt>{{ t("store.design.total") }}</dt><dd class="num">{{ formatMoney(total) }}</dd></div>
        </dl>
        <p v-else class="hint">{{ t("store.design.choose") }}</p>

        <LiveNotice :message="notice" />
        <p v-if="cart.locked" class="notice ok">{{ t("store.design.locked") }}</p>

        <label class="check ack">
          <input v-model="acknowledged" type="checkbox" name="acknowledged" :disabled="!chosen" />
          <span>{{ textFields.length ? t("store.design.acknowledgeText") : t("store.design.acknowledge") }}</span>
        </label>
        <button type="submit" class="btn primary" :disabled="!canAdd">{{ adding ? t("store.design.adding") : t("store.design.add") }}</button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.design { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 20px; align-items: start; }
.shot { aspect-ratio: 4 / 3; overflow: hidden; border: 1px solid var(--line); border-radius: calc(var(--radius) * 2); background: var(--brand-soft); }
.shot img { display: block; inline-size: 100%; block-size: 100%; object-fit: contain; }
.thumbs { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 0; padding: 0; list-style: none; }
.thumbs button { display: block; inline-size: 72px; block-size: 54px; padding: 0; overflow: hidden; border: 2px solid var(--line); border-radius: var(--radius); background: var(--surface); cursor: pointer; }
.thumbs button.active { border-color: var(--accent); }
.thumbs img { display: block; inline-size: 100%; block-size: 100%; object-fit: cover; }
.info { display: flex; flex-direction: column; gap: 14px; }
.info h2 { margin: 0; font-size: 20px; }
.info h3 { margin: 0 0 6px; font-size: 16px; }
.about, .hint { margin: 0; }
.facts { margin: 0; }
.facts div, .offers li, .sums div { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.facts dd, .sums dd { margin: 0; }
.order, .variants { display: flex; flex-direction: column; gap: 14px; }
.offers { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.offers li { padding-block-end: 6px; border-block-end: 1px dashed var(--line); }
.personalize { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; border: 0; }
.personalize legend { padding: 0; margin-block-end: 6px; font-weight: 600; }
.qty { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.qty input { inline-size: 96px; }
.sums { margin: 0; display: grid; gap: 4px; }
.sums .grand { font-weight: 700; font-size: 18px; }
.btn.primary { align-self: flex-start; }
@media (max-width: 760px) {
  .design { grid-template-columns: minmax(0, 1fr); }
}
</style>
