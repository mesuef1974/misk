<script setup lang="ts">
// القفل بإكساء الشريط (brand/misk/lockup-ribbon، اعتمده المالك 2026-11-20): نسخة PNG بحبر السمة المختارة.
// صورة عرض للفاتح؛ في الداكن يذوب حبر السمة في الخلفية فيُعرض القفل المسطّح (BrandLockup) بحبره الأبيض.
// كل نسخة ملف مستقل تبنيه Vite ببصمة؛ المتصفح ينزّل نسخة السمة الجارية وحدها.
import { computed } from "vue";
import BrandLockup from "@/components/BrandLockup.vue";
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
const trim = computed(() => `${-Math.round((imageHeight.value - props.height) / 2)}px`);
</script>

<template>
  <span class="brand-lockup-ribbon">
    <img
      v-if="src"
      class="ribbon"
      :src="src"
      :width="imageWidth"
      :height="imageHeight"
      alt=""
      decoding="async"
    />
    <BrandLockup class="flat" :class="{ always: !src }" :height="height" />
  </span>
</template>

<style scoped>
.brand-lockup-ribbon {
  display: inline-flex;
  align-items: center;
  max-inline-size: 100%;
}

.ribbon {
  display: block;
  max-inline-size: 100%;
  block-size: auto;
  /* الهامش الشفاف في الصورة يُطوى كي يحاذي القفل ما حوله كما يحاذيه المسطّح. */
  margin-block: v-bind(trim);
}

.flat:not(.always) {
  display: none;
}

/* الوضع الداكن بالمنطق نفسه في styles/base.css: النظام ما لم يفرض data-theme غيره. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .ribbon {
    display: none;
  }
  :root:not([data-theme="light"]) .flat {
    display: block;
  }
}

:root[data-theme="dark"] .ribbon {
  display: none;
}
:root[data-theme="dark"] .flat {
  display: block;
}
</style>
