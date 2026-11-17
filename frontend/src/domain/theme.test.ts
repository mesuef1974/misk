import { createPinia, setActivePinia } from "pinia";
import { nextTheme, parseTheme, THEME_KEY } from "@/domain/theme";
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
