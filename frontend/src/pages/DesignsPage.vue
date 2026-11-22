<script setup lang="ts">
import { onMounted } from "vue";
import { useI18n } from "vue-i18n";
import DesignCard from "@/components/DesignCard.vue";
import { useDesignsStore } from "@/stores/designs";

const { t } = useI18n();
const store = useDesignsStore();

onMounted(() => store.ensureLoaded());
</script>

<template>
  <h1>{{ t("store.designs.heading") }}</h1>
  <p class="lead">{{ t("store.designs.lead") }}</p>

  <div v-if="store.loadError" class="notice" role="alert">
    {{ store.loadError }}
    <button type="button" class="btn retry" @click="store.load()">{{ t("store.products.retry") }}</button>
  </div>

  <ul v-else-if="store.designs.length" class="product-grid">
    <li v-for="design in store.designs" :key="design.slug"><DesignCard :design="design" /></li>
  </ul>

  <div v-else-if="store.loaded" class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ t("store.designs.empty") }}</p>
    </div>
  </div>
</template>

<style scoped>
.retry { margin-inline-start: 12px; }
</style>
