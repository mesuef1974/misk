<script setup lang="ts">
// بطاقة منتج في المتجر: الاسم والوصف والمقاس والسعر، وكلها رابط واحد إلى المصمِّم.
import { useI18n } from "vue-i18n";
import BrandIcon from "@/components/BrandIcon.vue";
import { formatMoney } from "@/domain/orders";
import { localized } from "@/domain/store";
import type { StoreTemplate } from "@/services/store";

defineProps<{ product: StoreTemplate }>();
const { t } = useI18n();

const number = (value: string) => String(Number(value));
</script>

<template>
  <RouterLink class="product-card" :to="{ name: 'product', params: { slug: product.slug } }">
    <span class="top">
      <BrandIcon name="name" />
      <b>{{ localized(product.name, product.name_en) }}</b>
    </span>
    <span v-if="localized(product.description, product.description_en)" class="muted about">
      {{ localized(product.description, product.description_en) }}
    </span>
    <span class="meta">
      <span class="num muted">{{ t("store.products.size", { width: number(product.width_mm), height: number(product.height_mm) }) }}</span>
      <span v-if="product.allows_religious_text" class="pill">{{ t("store.products.religious") }}</span>
    </span>
    <span class="foot">
      <b class="num price">{{ t("store.products.price", { price: formatMoney(product.base_price) }) }}</b>
      <span class="go">{{ t("store.products.design") }}</span>
    </span>
  </RouterLink>
</template>

<style scoped>
.product-card {
  display: flex; flex-direction: column; gap: 10px; padding: 20px; min-inline-size: 0;
  border: 1px solid var(--line); border-radius: calc(var(--radius) * 2); background: var(--surface);
  color: var(--ink); text-decoration: none;
}
.product-card:hover { border-color: var(--accent); }
.top { display: flex; align-items: center; gap: 10px; font-family: var(--font-heading); font-size: 20px; line-height: 1.4; }
.about { font-size: 15px; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 14px; }
.foot { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; margin-block-start: auto; padding-block-start: 10px; border-block-start: 1px dashed var(--line); }
.price { font-size: 18px; }
.go { color: var(--accent); font-weight: 600; font-size: 15px; }
</style>
