<script setup lang="ts">
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const STEPS = ["catalog", "orders", "production"] as const;
</script>

<template>
  <h1>{{ t("about.heading") }}</h1>
  <p class="lead">{{ t("about.lead") }}</p>
  <ol class="steps">
    <li v-for="step in STEPS" :key="step">
      <strong>{{ t(`about.steps.${step}.title`) }}</strong> {{ t(`about.steps.${step}.body`) }}
    </li>
  </ol>
  <p class="muted">{{ t("about.audit") }}</p>
</template>

<style scoped>
.steps { padding-inline-start: 24px; display: grid; gap: 8px; }
</style>
