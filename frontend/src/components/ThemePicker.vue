<script setup lang="ts">
// منتقي المظهر: السمة (عشر، لكل منها نهارها وليلها) والوضع (تلقائي، نهاري، ليلي). الاختيار يسري فورًا ويُحفظ في المتصفح
// بالمفتاحين اللذين تقرؤهما لوحة Django. اللوحة popover أصلي: تُغلق بـ Esc وبالنقر خارجها ويعود التركيز إلى الزر.
// أزرار راديو حقيقية: الأسهم تنتقل بين السمات والقارئ الآلي يعلن الاسم والحالة.
import { useI18n } from "vue-i18n";
import { PALETTES, THEMES } from "@/domain/theme";
import { useThemeStore } from "@/stores/theme";

const theme = useThemeStore();
const { t } = useI18n();
</script>

<template>
  <button
    type="button"
    class="nav-item theme-switch"
    popovertarget="theme-picker"
    :aria-label="t('theme.buttonLabel', { palette: t(`theme.palettes.${theme.palette}`), mode: t(`theme.modes.${theme.theme}`) })"
  >
    <span class="tint current" aria-hidden="true"></span>
    <span>{{ t("theme.button") }}</span>
  </button>
  <div id="theme-picker" class="picker" popover role="dialog" :aria-label="t('theme.dialog')">
    <fieldset class="group">
      <legend>{{ t("theme.palette") }}</legend>
      <div class="swatches">
        <label v-for="p in PALETTES" :key="p.id" class="swatch" :data-palette="p.id">
          <input
            class="visually-hidden"
            type="radio"
            name="palette"
            :value="p.id"
            :checked="theme.palette === p.id"
            @change="theme.setPalette(p.id)"
          />
          <span class="tint" aria-hidden="true"></span>
          <span class="name">{{ t(`theme.palettes.${p.id}`) }}</span>
        </label>
      </div>
    </fieldset>
    <fieldset class="group">
      <legend>{{ t("theme.mode") }}</legend>
      <div class="modes">
        <label v-for="mode in THEMES" :key="mode" class="mode">
          <input
            class="visually-hidden"
            type="radio"
            name="theme-mode"
            :value="mode"
            :checked="theme.theme === mode"
            @change="theme.setTheme(mode)"
          />
          <span>{{ t(`theme.modes.${mode}`) }}</span>
        </label>
      </div>
      <p class="hint">{{ t("theme.hint") }}</p>
    </fieldset>
  </div>
</template>

<style scoped>
.theme-switch { anchor-name: --theme-switch; display: flex; align-items: center; gap: 10px; }

/* العيّنة تأخذ ألوانها من قاعدة السمة نفسها في tokens.css: data-palette على العنصر يضبط متغيّراتها له.
   نهارًا لون السمة بإطار شامبانيا، وليلًا خلفيتها الليلية بإطار لون تمييزها. */
.tint {
  flex: none;
  inline-size: 36px;
  aspect-ratio: 1;
  border-radius: 50%;
  background: light-dark(var(--day-color), var(--night-bg));
  border: 3px solid light-dark(var(--champagne), var(--night-accent));
  box-sizing: border-box;
}
.tint.current { inline-size: 18px; border-width: 2px; }

.picker {
  inline-size: min(340px, calc(100vw - 32px));
  max-block-size: calc(100dvh - 32px);
  overflow: auto;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 12px 32px color-mix(in srgb, var(--ink) 22%, transparent);
}
.picker::backdrop { background: color-mix(in srgb, var(--ink) 28%, transparent); }

/* حيث يدعم المتصفح الربط بالمرساة والشاشة عريضة: اللوحة فوق زرّها في الشريط الجانبي. وإلا فهي في وسط الشاشة. */
@supports (anchor-name: --a) {
  @media (min-width: 861px) {
    .picker {
      position-anchor: --theme-switch;
      inset: auto;
      inset-block-end: anchor(top);
      inset-inline-start: anchor(start);
      margin: 0 0 8px;
      position-try-fallbacks: flip-block, flip-inline;
    }
    .picker::backdrop { background: none; }
  }
}

.group { margin: 0; padding: 0; border: 0; min-inline-size: 0; }
.group + .group { margin-block-start: 16px; padding-block-start: 16px; border-block-start: 1px solid var(--line); }
legend { padding: 0; margin-block-end: 10px; font-family: var(--font-heading); font-weight: 700; font-size: 14px; }

.swatches { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px 4px; }
.swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 6px 2px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}
.swatch:hover { color: var(--ink); background: var(--raised); }
.swatch:has(input:checked) { color: var(--ink); font-weight: 700; }
.swatch:has(input:checked) .tint { outline: 2px solid var(--ink); outline-offset: 2px; }
.swatch:has(input:focus-visible), .mode:has(input:focus-visible) { outline: 3px solid var(--focus); outline-offset: 1px; }

.modes { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--line-strong); border-radius: var(--radius); overflow: hidden; }
.mode { position: relative; display: grid; place-items: center; min-block-size: 40px; cursor: pointer; font-size: 14px; }
.mode + .mode { border-inline-start: 1px solid var(--line-strong); }
.mode:has(input:checked) { background: var(--accent); color: var(--on-accent); font-weight: 700; }
.hint { margin: 10px 0 0; font-size: 12px; color: var(--muted); }

.visually-hidden {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}
.swatch { position: relative; }
</style>
