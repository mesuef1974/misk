<script setup lang="ts">
// صفحات الثقة (الأسئلة الشائعة، الاسترجاع، الخصوصية، الشروط): صفحة واحدة ونصها من ملفات الترجمة.
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const SECTIONS = {
  faq: ["order", "ready", "edit", "religious", "pickup", "payment"],
  returns: ["cancel", "defect", "spelling", "review"],
  privacy: ["collect", "payment", "cookies", "tracking", "rights"],
  terms: ["custom", "price", "dates", "content", "law"],
} as const;

const props = defineProps<{ topic: keyof typeof SECTIONS }>();
const { t } = useI18n();
const sections = computed(() => SECTIONS[props.topic]);
</script>

<template>
  <h1>{{ t(`store.policy.${topic}.heading`) }}</h1>
  <p class="lead">{{ t(`store.policy.${topic}.lead`) }}</p>
  <div class="sections">
    <section v-for="section in sections" :key="section" class="panel">
      <h2>{{ t(`store.policy.${topic}.${section}.title`) }}</h2>
      <p>{{ t(`store.policy.${topic}.${section}.body`) }}</p>
    </section>
  </div>
</template>

<style scoped>
.sections { display: grid; gap: 12px; max-inline-size: 760px; }
h2 { margin-block: 0 6px; font-size: 18px; color: var(--accent); }
p { margin: 0; }
</style>
