<script setup lang="ts">
import { computed } from "vue";
import { statusLabel } from "@/domain/orders";

const props = defineProps<{ status: string }>();
const label = computed(() => statusLabel(props.status));
</script>

<template>
  <span class="badge" :class="`is-${status}`">{{ label }}</span>
</template>

<style scoped>
.badge {
  display: inline-block; padding-inline: 10px; border: 1px solid var(--line); border-radius: 999px;
  font-size: 14px; line-height: 1.9; white-space: nowrap; color: var(--muted); background: var(--bg);
}
.is-confirmed, .is-in_production, .is-ready { border-color: var(--accent); color: var(--accent); }
.is-delivered { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.is-cancelled { border-color: var(--risk); color: var(--risk); }
</style>
