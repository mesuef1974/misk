<script setup lang="ts">
// شعار الشريط الحريري (PNG المعتمد) بلون السمة المختارة: لكل سمة ملفها static/brand/logo/misk-<السمة>.png،
// يولّدها scripts/build_theme_logos.py من الأصل brand/misk/misk-logo-ribbon.png. يُجلب ملف السمة المختارة وحده.
import { computed } from "vue";
import { useThemeStore } from "@/stores/theme";

withDefaults(defineProps<{ height?: number }>(), { height: 96 });

const files = import.meta.glob<string>("../static/brand/logo/misk-*.png", { eager: true, query: "?url", import: "default" });
const theme = useThemeStore();
const src = computed(() => files[`../static/brand/logo/misk-${theme.palette}.png`]);
</script>

<template>
  <img class="ribbon-logo" :src="src" :height="height" alt="" decoding="async" />
</template>

<style scoped>
.ribbon-logo {
  flex: none;
  display: block;
  inline-size: auto;
  max-inline-size: 100%;
}
</style>
