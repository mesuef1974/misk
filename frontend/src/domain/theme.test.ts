import { createPinia, setActivePinia } from "pinia";
import { nextTheme, PALETTE_KEY, PALETTES, parsePalette, parseTheme, THEME_KEY } from "@/domain/theme";
import { useThemeStore } from "@/stores/theme";

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("وضع الألوان", () => {
  it("يقبل قيم لوحة Django وحدها", () => {
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("dark")).toBe("dark");
    for (const bad of ["auto", "blue", "", null, undefined, 1]) expect(parseTheme(bad)).toBe("auto");
  });

  it("يدور بترتيب اللوحة: المخالف لوضع النظام أولًا", () => {
    expect([nextTheme("auto", true), nextTheme("light", true), nextTheme("dark", true)]).toEqual(["light", "dark", "auto"]);
    expect([nextTheme("auto", false), nextTheme("dark", false), nextTheme("light", false)]).toEqual(["dark", "light", "auto"]);
  });

  it("يقرأ اختيار اللوحة المحفوظ ويطبّقه", () => {
    localStorage.setItem(THEME_KEY, "light");
    expect(useThemeStore().theme).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("يحفظ التبديل بالمفتاح الذي تقرؤه اللوحة", () => {
    const store = useThemeStore();
    expect(store.theme).toBe("auto");
    store.cycle();
    expect(store.theme).not.toBe("auto");
    expect(localStorage.getItem(THEME_KEY)).toBe(store.theme);
    expect(document.documentElement.dataset.theme).toBe(store.theme);
  });

  it("يتبع تغييرًا جاء من تبويب آخر ويتجاهل مفاتيح غيره", () => {
    const store = useThemeStore();
    store.onStorage(new StorageEvent("storage", { key: "other", newValue: "dark" }));
    expect(store.theme).toBe("auto");
    store.onStorage(new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }));
    expect(store.theme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("السمة", () => {
  beforeEach(() => {
    delete document.documentElement.dataset.palette;
  });

  it("عشر سمات والعودي افتراضي لكل قيمة غير معروفة", () => {
    expect(PALETTES).toHaveLength(10);
    expect(parsePalette("navy")).toBe("navy");
    for (const bad of ["green", "", null, undefined, 1]) expect(parsePalette(bad)).toBe("oud");
  });

  it("الاختيار يُوضع على الصفحة ويُحفظ ولا يمسّ الوضع", () => {
    const store = useThemeStore();
    expect(document.documentElement.dataset.palette).toBe("oud");
    store.setPalette("teal");
    expect(document.documentElement.dataset.palette).toBe("teal");
    expect(localStorage.getItem(PALETTE_KEY)).toBe("teal");
    expect(store.theme).toBe("auto");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("يقرأ المحفوظ عند البدء ويتبع تغيير تبويب آخر", () => {
    localStorage.setItem(PALETTE_KEY, "rose");
    const store = useThemeStore();
    expect(store.palette).toBe("rose");
    store.onStorage(new StorageEvent("storage", { key: PALETTE_KEY, newValue: "black" }));
    expect(document.documentElement.dataset.palette).toBe("black");
  });

  it("الوضع يُضبط مباشرة من المنتقي", () => {
    const store = useThemeStore();
    store.setTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
  });
});
