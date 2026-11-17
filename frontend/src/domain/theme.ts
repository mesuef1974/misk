// وضع الألوان: مفتاح واحد يحكم المنصة ولوحة Django. اللوحة تحفظ اختيارها في localStorage["theme"]
// وتضعه في data-theme على <html> (admin/js/theme.js)؛ المنصة تقرأ المفتاح نفسه وتكتبه بالقيم نفسها.

export type Theme = "auto" | "light" | "dark";

export const THEME_KEY = "theme";
export const THEME_LABELS: Record<Theme, string> = { auto: "تلقائي", light: "فاتح", dark: "داكن" };

export function parseTheme(value: unknown): Theme {
  return value === "light" || value === "dark" ? value : "auto";
}

/** الترتيب نفسه في لوحة Django: بعد «تلقائي» يأتي الوضع المخالف لوضع النظام كي يظهر أثر الضغطة الأولى. */
export function nextTheme(current: Theme, systemDark: boolean): Theme {
  const order: Theme[] = systemDark ? ["auto", "light", "dark"] : ["auto", "dark", "light"];
  return order[(order.indexOf(current) + 1) % order.length];
}

/** التخزين قد يكون محجوبًا (نافذة خاصة): الوضع يبقى تلقائيًّا ولا يُرمى خطأ. */
export function readStoredTheme(): Theme {
  try {
    return parseTheme(localStorage.getItem(THEME_KEY));
  } catch {
    return "auto";
  }
}

export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // الاختيار يسري في هذه الصفحة وحدها.
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}
