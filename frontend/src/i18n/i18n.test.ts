import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { localeFromPath, localeParam, localizePath, otherLocale, stripLocale } from "@/domain/locale";
import { safeNext } from "@/domain/navigation";
import { currentLocale, i18n, setLocale } from "@/i18n";
import { installLocale } from "@/i18n/router";
import ar from "@/i18n/locales/ar";
import en from "@/i18n/locales/en";
import { routes } from "@/router";
import { sessionService } from "@/services/session";

vi.mock("@/services/session", () => ({
  sessionService: { me: vi.fn().mockResolvedValue(null), login: vi.fn(), logout: vi.fn() },
}));

let router: Router;

beforeEach(() => {
  setActivePinia(createPinia());
  router = createRouter({ history: createMemoryHistory(), routes });
  installLocale(router);
  vi.mocked(sessionService.me).mockResolvedValue(null);
});

function alternates(): Record<string, string> {
  const links = document.head.querySelectorAll<HTMLLinkElement>("link[rel='alternate'][hreflang]");
  return Object.fromEntries([...links].map((link) => [link.hreflang, link.getAttribute("href") ?? ""]));
}

/** مفاتيح الرسائل كلها بمساراتها: `home.traits.warm.title`. */
function keys(tree: object, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [prefix + key] : keys(value as object, `${prefix}${key}.`),
  );
}

describe("اللغة من المسار", () => {
  it("`/en` وما تحته إنجليزي، وما يبدأ بحروفها فقط عربي", () => {
    expect(localeFromPath("/en")).toBe("en");
    expect(localeFromPath("/en/about")).toBe("en");
    expect(localeFromPath("/")).toBe("ar");
    expect(localeFromPath("/about")).toBe("ar");
    expect(localeFromPath("/engraving")).toBe("ar");
    expect(localeFromPath("/orders/en")).toBe("ar");
  });

  it("يحوّل المسار بين اللغتين ذهابًا وعودة", () => {
    expect(stripLocale("/en")).toBe("/");
    expect(stripLocale("/en/track/abc")).toBe("/track/abc");
    expect(stripLocale("/about")).toBe("/about");
    expect(localizePath("/", "en")).toBe("/en");
    expect(localizePath("/about", "en")).toBe("/en/about");
    expect(localizePath("/en/about", "en")).toBe("/en/about");
    expect(localizePath("/en/about", "ar")).toBe("/about");
    expect(localizePath("/en", "ar")).toBe("/");
    expect(localeParam("ar")).toBe("");
    expect(localeParam("en")).toBe("en");
    expect(otherLocale("ar")).toBe("en");
  });
});

describe("ملفا الترجمة", () => {
  it("المفاتيح نفسها في اللغتين ولا نص فارغ", () => {
    expect(keys(en).sort()).toEqual(keys(ar).sort());
    for (const tree of [ar, en]) {
      const empty = keys(tree).filter((key) => !key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], tree));
      expect(empty).toEqual([]);
    }
  });

  it("الإنجليزية لا تُحمَّل قبل طلبها", async () => {
    // الوحدة تبدأ بالعربية وحدها؛ ما حمّله اختبار سابق يبقى، فالفحص على الترتيب داخل هذا الملف.
    expect(i18n.global.availableLocales).toContain("ar");
    await setLocale("en");
    expect(i18n.global.availableLocales).toContain("en");
    expect(i18n.global.t("notFound.heading")).toBe("Page not found");
  });
});

describe("المسارات بلغتين", () => {
  it("الصفحة العامة تُفتح بالمسارين وتضبط لغة المستند واتجاهه", async () => {
    await router.push("/en/about");
    expect(router.currentRoute.value.name).toBe("about");
    expect(currentLocale()).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");

    await router.push("/about");
    expect(router.currentRoute.value.name).toBe("about");
    expect(currentLocale()).toBe("ar");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("التنقّل بالاسم بين الصفحات العامة يبقي الزائر في لغته", async () => {
    await router.push("/en/about");
    await router.push({ name: "home" });
    expect(router.currentRoute.value.fullPath).toBe("/en");

    await router.push("/about");
    await router.push({ name: "home" });
    expect(router.currentRoute.value.fullPath).toBe("/");
  });

  it("مسارات الورشة تُفتح بلغتين والتنقّل بالاسم يبقي لغتها", async () => {
    await router.push("/en/about");
    await router.push({ name: "login" });
    expect(router.currentRoute.value.fullPath).toBe("/en/login");
    expect(currentLocale()).toBe("en");

    await router.push("/en/orders/7");
    expect(router.currentRoute.value.name).toBe("order-detail");
    expect(router.currentRoute.value.meta.requiresStaff).toBe(true);
    await router.push({ name: "production" });
    expect(router.currentRoute.value.fullPath).toBe("/en/production");

    await router.push("/orders");
    await router.push({ name: "materials" });
    expect(router.currentRoute.value.fullPath).toBe("/materials");
    expect(currentLocale()).toBe("ar");
  });

  it("hreflang للصفحات ذات النسختين وحدها", async () => {
    await router.push("/en/about");
    const origin = window.location.origin;
    expect(alternates()).toEqual({
      ar: `${origin}/about`,
      en: `${origin}/en/about`,
      "x-default": `${origin}/about`,
    });

    await router.push("/");
    expect(alternates()).toEqual({ ar: `${origin}/`, en: `${origin}/en`, "x-default": `${origin}/` });

    await router.push("/no-such-page");
    expect(alternates()).toEqual({});
  });
});

describe("القشرة بالإنجليزية", () => {
  async function shell(path: string) {
    const { default: App } = await import("@/App.vue");
    await router.push(path);
    const app = mount(App, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();
    return app;
  }

  it("مبدِّل اللغة يفتح الصفحة نفسها باللغة الأخرى", async () => {
    const app = await shell("/en/about");
    const toArabic = app.find('a[lang="ar"]');
    expect(toArabic.text()).toBe("العربية");
    expect(toArabic.attributes("href")).toBe("/about");
    expect(app.find("h1").text()).toBe("About");
    expect(document.title).toBe("Misk");

    await toArabic.trigger("click");
    await flushPromises();
    expect(app.find("h1").text()).toBe("عن المنصة");
    const toEnglish = app.find('a[lang="en"]');
    expect(toEnglish.text()).toBe("English");
    expect(toEnglish.attributes("href")).toBe("/en/about");
    app.unmount();
  });

  it("صفحة الدخول ومنتقي المظهر بالإنجليزية تحت `/en`", async () => {
    const app = await shell("/en/login");
    expect(app.find("h1").text()).toBe("Sign in");
    expect(app.find('a[lang="ar"]').attributes("href")).toBe("/login");
    expect(app.find(".theme-switch").text()).toBe("Appearance");
    expect(app.find("#theme-picker legend").text()).toBe("Palette");
    app.unmount();
  });

  it("لا مبدِّل في «غير موجودة»: لا مسار مقابل لها", async () => {
    const app = await shell("/no-such-page");
    expect(app.find("a[lang]").exists()).toBe(false);
    app.unmount();
  });

  it("وجهة ما بعد الدخول لا تعود إلى صفحة الدخول بأي لغة", () => {
    expect(safeNext("/en/login")).toBe("/");
    expect(safeNext("/en/login?next=/a")).toBe("/");
    expect(safeNext("/en/orders/5")).toBe("/en/orders/5");
  });

  it("صفحة «غير موجودة» تحت `/en` إنجليزية ورابطها إلى الرئيسية الإنجليزية", async () => {
    const app = await shell("/en/no-such-page");
    expect(app.find("h1").text()).toBe("Page not found");
    expect(app.find("a.home").attributes("href")).toBe("/en");
    app.unmount();
  });
});
