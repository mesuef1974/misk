<script setup lang="ts">
// القفل بإكساء الشريط (brand/misk/lockup-ribbon، اعتمده المالك 2026-11-20): نسخة PNG بحبر السمة المختارة،
// في الوضعين الفاتح والليلي بأمر المالك. كل نسخة ملف مستقل تبنيه Vite ببصمة؛ المتصفح ينزّل نسخة السمة الجارية وحدها.
// في الصفحات الإنجليزية نسخة «Misk» (الملفات -en-، العقدة يسار الكلمة، من حزمة المالك 2026-11-21) بالمقاس والهامش نفسيهما.
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { DEFAULT_LOCALE, type Locale } from "@/domain/locale";
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

function sourceFor(locale: Locale, palette: string): string | undefined {
  const variant = locale === DEFAULT_LOCALE ? "" : `${locale}-`;
  return sources[`../static/brand/logo/misk-lockup-ribbon-${variant}${palette}.png`];
}

const theme = useThemeStore();
const { locale } = useI18n();
const src = computed(() => {
  const current = locale.value as Locale;
  return sourceFor(current, theme.palette) ?? sourceFor(current, DEFAULT_PALETTE) ?? sourceFor(DEFAULT_LOCALE, DEFAULT_PALETTE);
});
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
