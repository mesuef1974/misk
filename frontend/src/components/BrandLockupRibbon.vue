<script setup lang="ts">
// القفل بإكساء الشريط (brand/misk/lockup-ribbon، اعتمده المالك 2026-11-20): نسخة PNG بحبر السمة المختارة،
// في الوضعين الفاتح والليلي بأمر المالك. كل نسخة ملف مستقل تبنيه Vite ببصمة؛ المتصفح ينزّل نسخة السمة الجارية وحدها.
import { computed } from "vue";
import { DEFAULT_PALETTE } from "@/domain/theme";
import { useThemeStore } from "@/stores/theme";

const props = withDefaults(defineProps<{ height?: number }>(), { height: 40 });

// الصورة 1600×571 وحول القفل فيها هامش شفاف: ارتفاع القفل المرئي نحو ثلثيها.
const IMAGE_RATIO = 1600 / 571;
const VISIBLE_SHARE = 0.665;

const sources = import.meta.glob<string>("../static/brand/logo/misk-lockup-ribbon-*.png", {
  query: "?url",
  import: "default",
  eager: true,
});

function sourceFor(palette: string): string | undefined {
  return sources[`../static/brand/logo/misk-lockup-ribbon-${palette}.png`];
}

const theme = useThemeStore();
const src = computed(() => sourceFor(theme.palette) ?? sourceFor(DEFAULT_PALETTE));
const imageHeight = computed(() => Math.round(props.height / VISIBLE_SHARE));
const imageWidth = computed(() => Math.round(imageHeight.value * IMAGE_RATIO));
// الهامش الشفاف يُطوى كي يحاذي القفل ما حوله بارتفاعه المرئي.
const trim = computed(() => `${-Math.round((imageHeight.value - props.height) / 2)}px`);
</script>

<template>
  <img class="brand-lockup-ribbon" :src="src" :width="imageWidth" :height="imageHeight" alt="" decoding="async" />
</template>

<style scoped>
.brand-lockup-ribbon {
  display: block;
  flex: none;
  max-inline-size: 100%;
  block-size: auto;
  margin-block: v-bind(trim);
}
</style>
