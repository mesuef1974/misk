<script setup lang="ts">
defineProps<{ ok: boolean | null }>();
</script>

<template>
  <div class="card" :class="{ ok: ok === true, bad: ok === false }" role="status">
    <strong v-if="ok === null">يتحقق من الخادم…</strong>
    <strong v-else-if="ok">الخادم يعمل</strong>
    <strong v-else>الخادم لا يستجيب</strong>
  </div>
</template>

<style scoped>
.card { border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; background: var(--surface); }
.card.ok { border-inline-start: 4px solid var(--accent); }
.card.bad { border-inline-start: 4px solid var(--risk); }
</style>
