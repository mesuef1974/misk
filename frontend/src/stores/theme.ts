import { ref } from "vue";
import { defineStore } from "pinia";
import { applyTheme, nextTheme, parseTheme, readStoredTheme, storeTheme, THEME_KEY, type Theme } from "@/domain/theme";

export const useThemeStore = defineStore("theme", () => {
  const theme = ref<Theme>(readStoredTheme());
  applyTheme(theme.value);

  function cycle(): void {
    const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
    theme.value = nextTheme(theme.value, systemDark);
    storeTheme(theme.value);
    applyTheme(theme.value);
  }

  /** تغيير من تبويب آخر (المنصة أو لوحة Django) يصل هذا التبويب دون إعادة تحميل. */
  function onStorage(event: StorageEvent): void {
    if (event.key !== THEME_KEY) return;
    theme.value = parseTheme(event.newValue);
    applyTheme(theme.value);
  }

  return { theme, cycle, onStorage };
});
