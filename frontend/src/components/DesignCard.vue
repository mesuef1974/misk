<script setup lang="ts">
// بطاقة تصميم جاهز: صورة العرض والاسم والسعر الذي يبدأ منه، وكلها رابط واحد إلى صفحته.
import { useI18n } from "vue-i18n";
import { formatMoney } from "@/domain/orders";
import { localized } from "@/domain/store";
import type { StoreDesign } from "@/services/store";

defineProps<{ design: StoreDesign }>();
const { t } = useI18n();
</script>

<template>
  <RouterLink class="design-card" :to="{ name: 'design', params: { slug: design.slug } }">
    <span class="shot">
      <img
        v-if="design.image"
        :src="`${design.image.url}?w=480`"
        :alt="localized(design.image.alt, design.image.alt_en)"
        loading="lazy"
        decoding="async"
      />
    </span>
    <b class="name">{{ localized(design.name, design.name_en) }}</b>
    <span class="foot">
      <b class="num price">{{ t("store.designs.from", { price: formatMoney(design.price_from) }) }}</b>
      <span class="go">{{ t("store.designs.view") }}</span>
    </span>
  </RouterLink>
</template>

<style scoped>
.design-card {
  display: flex; flex-direction: column; gap: 10px; padding: 12px; min-inline-size: 0; block-size: 100%;
  border: 1px solid var(--line); border-radius: calc(var(--radius) * 2); background: var(--surface);
  color: var(--ink); text-decoration: none;
}
.design-card:hover { border-color: var(--accent); }
.shot { display: block; aspect-ratio: 4 / 3; overflow: hidden; border-radius: var(--radius); background: var(--brand-soft); }
.shot img { display: block; inline-size: 100%; block-size: 100%; object-fit: cover; }
.name { padding-inline: 8px; font-family: var(--font-heading); font-size: 19px; line-height: 1.4; }
.foot {
  display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px;
  margin-block-start: auto; padding: 10px 8px 6px; border-block-start: 1px dashed var(--line);
}
.price { font-size: 17px; }
.go { color: var(--accent); font-weight: 600; font-size: 15px; }
</style>
