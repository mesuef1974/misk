<script setup lang="ts">
// أيقونات الهوية كما هي من brand/misk/identity/icons (نسخة في static/brand/icons يطابقها tests/test_brand.py).
// تُحقن نصًّا لترث لون النص (stroke="currentColor")؛ المصدر ملفات ثابتة في المستودع لا مدخل مستخدم.
import { computed } from "vue";

const sources = import.meta.glob<string>("../static/brand/icons/*.svg", { query: "?raw", import: "default", eager: true });
const ICONS: Record<string, string> = Object.fromEntries(
  Object.entries(sources).map(([path, svg]) => [path.slice(path.lastIndexOf("/") + 1, -4), svg]),
);

const props = defineProps<{ name: string }>();
const svg = computed(() => ICONS[props.name] ?? "");
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <span v-if="svg" class="ic" aria-hidden="true" v-html="svg"></span>
</template>
