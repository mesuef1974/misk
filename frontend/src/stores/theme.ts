import { ref } from "vue";
import { defineStore } from "pinia";
import {
  applyPalette,
  applyTheme,
  nextTheme,
  PALETTE_KEY,
  parsePalette,
  parseTheme,
  readStoredPalette,
  readStoredTheme,
  storePalette,
  storeTheme,
  THEME_KEY,
  type Palette,
  type Theme,
} from "@/domain/theme";

export const useThemeStore = defineStore("theme", () => {
  const theme = ref<Theme>(readStoredTheme());
  const palette = ref<Palette>(readStoredPalette());
  applyTheme(theme.value);
  applyPalette(palette.value);

  function setTheme(value: Theme): void {
    theme.value = value;
    storeTheme(value);
    applyTheme(value);
  }

  function cycle(): void {
    const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
    setTheme(nextTheme(theme.value, systemDark));
  }

  function setPalette(value: Palette): void {
    palette.value = value;
    storePalette(value);
    applyPalette(value);
  }

  /** تغيير من تبويب آخر (المنصة أو لوحة Django) يصل هذا التبويب دون إعادة تحميل. */
  function onStorage(event: StorageEvent): void {
    if (event.key === THEME_KEY) {
      theme.value = parseTheme(event.newValue);
      applyTheme(theme.value);
    } else if (event.key === PALETTE_KEY) {
      palette.value = parsePalette(event.newValue);
      applyPalette(palette.value);
    }
  }

  return { theme, palette, setTheme, cycle, setPalette, onStorage };
});
