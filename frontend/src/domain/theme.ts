// وضع الألوان: مفتاح واحد يحكم المنصة ولوحة Django. اللوحة تحفظ اختيارها في localStorage["theme"]
// وتضعه في data-theme على <html> (admin/js/theme.js)؛ المنصة تقرأ المفتاح نفسه وتكتبه بالقيم نفسها.
// السمة (لون العلامة) اختيار ثانٍ مستقل: localStorage["palette"] وdata-palette على <html>.
// لكل سمة نهارها وليلها: السمة تحدد ألوان الوضعين، والوضع يختار أيّهما يُعرض.

export type Theme = "auto" | "light" | "dark";

export const THEME_KEY = "theme";
export const THEME_LABELS: Record<Theme, string> = { auto: "تلقائي", light: "نهاري", dark: "ليلي" };
export const THEMES: Theme[] = ["auto", "light", "dark"];

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

// السمات العشر بترتيب جدول الهوية؛ ألوانها في static/brand/tokens.css (--palette-<id>) لا هنا.
// الأسماء نفسها في tokens.css وapps/core/static/core/theme-init.js (tests/test_brand.py يطابقها).
export const PALETTES = [
  { id: "navy", label: "كحلي" },
  { id: "royal-blue", label: "أزرق ملكي" },
  { id: "teal", label: "فيروزي" },
  { id: "emerald", label: "زمردي" },
  { id: "olive", label: "زيتوني" },
  { id: "purple", label: "بنفسجي" },
  { id: "rose", label: "وردي" },
  { id: "chocolate", label: "شوكولاتي" },
  { id: "black", label: "أسود" },
  { id: "oud", label: "عودي" },
] as const;

export type Palette = (typeof PALETTES)[number]["id"];

export const PALETTE_KEY = "palette";
export const DEFAULT_PALETTE: Palette = "oud";

export function parsePalette(value: unknown): Palette {
  return PALETTES.find((p) => p.id === value)?.id ?? DEFAULT_PALETTE;
}

export function paletteLabel(palette: Palette): string {
  return PALETTES.find((p) => p.id === palette)?.label ?? "";
}

export function readStoredPalette(): Palette {
  try {
    return parsePalette(localStorage.getItem(PALETTE_KEY));
  } catch {
    return DEFAULT_PALETTE;
  }
}

export function storePalette(palette: Palette): void {
  try {
    localStorage.setItem(PALETTE_KEY, palette);
  } catch {
    // الاختيار يسري في هذه الصفحة وحدها.
  }
}

export function applyPalette(palette: Palette): void {
  document.documentElement.dataset.palette = palette;
}
