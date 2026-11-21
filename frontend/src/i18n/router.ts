import type { RouteLocationNormalized, Router } from "vue-router";
import { DEFAULT_LOCALE, LOCALES, localeFromPath, localizePath } from "@/domain/locale";
import { setLocale } from "@/i18n";

const HREFLANG = "link[rel='alternate'][hreflang]";

/** روابط hreflang للصفحات ذات النسختين (`meta.localized`) وحدها، من جدول المسارات نفسه.
 *  تُكتب في المتصفح ما دامت الواجهة SPA؛ حين تُصيَّر صفحات المتجر من الخادم تنتقل إلى القالب. */
export function syncAlternates(to: RouteLocationNormalized, origin = window.location.origin): void {
  document.head.querySelectorAll(HREFLANG).forEach((link) => link.remove());
  if (!to.meta.localized) return;
  const entries: [string, string][] = LOCALES.map((locale) => [locale, localizePath(to.path, locale)]);
  entries.push(["x-default", localizePath(to.path, DEFAULT_LOCALE)]);
  for (const [hreflang, path] of entries) {
    const link = document.createElement("link");
    link.rel = "alternate";
    link.hreflang = hreflang;
    link.href = origin + path;
    document.head.append(link);
  }
}

/** اللغة تتبع المسار عند كل انتقال: تُحمَّل رسائلها قبل عرض الصفحة فلا يظهر نص بلغة أخرى. */
export function installLocale(router: Router): void {
  router.beforeEach(async (to) => {
    await setLocale(localeFromPath(to.path));
    return true;
  });
  router.afterEach((to) => syncAlternates(to));
}
