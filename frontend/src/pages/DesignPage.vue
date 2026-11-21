<script setup lang="ts">
// صفحة تصميم جاهز: صور العرض والمقاس والنسخ بخاماتها وأسعارها. عرض فقط: الطلب يُفتح مع السلة
// (docs/ready-designs-plan.md، الطلب 2). الأسعار من الخادم كما هي، وملف التصميم لا يصل المتصفح.
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { materialName } from "@/domain/catalog";
import { formatMoney } from "@/domain/orders";
import { localized, storeError } from "@/domain/store";
import { currentLocale } from "@/i18n";
import { storeService, type StoreDesignDetail } from "@/services/store";

const props = defineProps<{ slug: string }>();
const { t, locale } = useI18n();

const detail = ref<StoreDesignDetail | null>(null);
const loadError = ref("");
const shown = ref(0);
let ticket = 0;

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
const image = computed(() => detail.value?.images[shown.value] ?? null);

async function load(): Promise<void> {
  const mine = ++ticket;
  loadError.value = "";
  detail.value = null;
  shown.value = 0;
  try {
    const result = await storeService.design(props.slug, currentLocale());
    if (mine === ticket) detail.value = result;
  } catch (error) {
    if (mine === ticket) loadError.value = storeError(error, t("errors.unexpected")).message;
  }
}

watch(() => props.slug, load, { immediate: true });
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
        <img v-if="image" :src="image.url" :alt="localized(image.alt, image.alt_en)" />
      </div>
      <ul v-if="detail.images.length > 1" class="thumbs">
        <li v-for="(item, index) in detail.images" :key="item.url">
          <button type="button" :class="{ active: index === shown }" :aria-pressed="index === shown" @click="shown = index">
            <img :src="item.url" :alt="localized(item.alt, item.alt_en)" loading="lazy" />
          </button>
        </li>
      </ul>
    </section>

    <section class="panel info">
      <p v-if="description" class="about">{{ description }}</p>
      <dl v-if="size" class="facts">
        <div><dt>{{ t("store.design.size") }}</dt><dd class="num">{{ size }}</dd></div>
      </dl>

      <h2>{{ t("store.design.options") }}</h2>
      <div v-for="variant in detail.variants" :key="variant.code" class="variant">
        <h3 v-if="detail.variants.length > 1 && variant.code">{{ t("store.design.variant", { code: variant.code }) }}</h3>
        <ul class="offers">
          <li v-for="offer in variant.offers" :key="offer.material.id">
            <span>{{ t("store.design.material", { name: materialName(offer.material), thickness: number(offer.material.thickness_mm) }) }}</span>
            <b class="num">{{ formatMoney(offer.price) }}</b>
          </li>
        </ul>
      </div>

      <button type="button" class="btn primary" disabled>{{ t("store.design.soon") }}</button>
      <p class="hint">{{ t("store.design.soonNote") }}</p>
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
.facts div, .offers li { display: flex; justify-content: space-between; gap: 12px; }
.facts dd { margin: 0; }
.offers { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.offers li { padding-block-end: 6px; border-block-end: 1px dashed var(--line); }
.btn.primary { align-self: flex-start; }
@media (max-width: 760px) {
  .design { grid-template-columns: minmax(0, 1fr); }
}
</style>
