<script setup lang="ts">
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import ProductCard from "@/components/ProductCard.vue";
import { useStorefrontStore } from "@/stores/storefront";

const { t } = useI18n();
const storefront = useStorefrontStore();

onMounted(() => storefront.ensureLoaded());
</script>

<template>
  <h1>{{ t("store.products.heading") }}</h1>
  <p class="lead">{{ t("store.products.lead") }}</p>

  <div v-if="storefront.loadError" class="notice" role="alert">
    {{ storefront.loadError }}
    <button type="button" class="btn retry" @click="storefront.load()">{{ t("store.products.retry") }}</button>
  </div>

  <ul v-else-if="storefront.templates.length" class="product-grid">
    <li v-for="product in storefront.templates" :key="product.slug"><ProductCard :product="product" /></li>
  </ul>

  <div v-else-if="storefront.loaded" class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ t("store.products.empty") }}</p>
    </div>
  </div>
</template>

<style scoped>
.retry { margin-inline-start: 12px; }
</style>
