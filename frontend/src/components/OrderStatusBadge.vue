<script setup lang="ts">
import { computed } from "vue";
import { statusLabel } from "@/domain/orders";

const props = defineProps<{ status: string }>();
const label = computed(() => statusLabel(props.status));
</script>

<template>
  <span class="pill badge" :class="`is-${status}`">{{ label }}</span>
</template>

<style scoped>
/* الشكل من .pill في base.css (حبّة الدليل)؛ الحالات المنتهية تتميّز بخلفيتها الناعمة. */
.is-delivered { background: var(--ok-soft); }
.is-cancelled, .is-refunded { background: var(--risk-soft); color: var(--risk); }
.is-draft, .is-awaiting_payment { background: var(--raised); }
</style>
