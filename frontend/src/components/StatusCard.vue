<script setup lang="ts">
import { useI18n } from "vue-i18n";

defineProps<{ ok: boolean | null }>();
const { t } = useI18n();
</script>

<template>
  <div class="card" :class="{ ok: ok === true, bad: ok === false }" role="status">
    <strong v-if="ok === null">{{ t("status.checking") }}</strong>
    <strong v-else-if="ok">{{ t("status.up") }}</strong>
    <strong v-else>{{ t("status.down") }}</strong>
  </div>
</template>

<style scoped>
.card { border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 18px; background: var(--surface); }
.card.ok { border-inline-start: 4px solid var(--ok); }
.card.bad { border-inline-start: 4px solid var(--risk); }
</style>
