// لغة الواجهة من المسار وحده: `/en` وما تحته إنجليزي، وكل ما عداه عربي (الافتراضي بلا بادئة).
// لا تفاوض بـ Accept-Language ولا تخزين: الرابط نفسه يعطي اللغة نفسها لكل زائر، وهو ما تشير إليه hreflang.
// لوحة الورشة بلغتين كالصفحات العامة؛ ما يرسله الخادم من نصوص (رسائل الرفض وأسماء المواد) يبقى كما خُزِّن.

export const LOCALES = ["ar", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "ar";
export const DIRECTIONS: Record<Locale, "rtl" | "ltr"> = { ar: "rtl", en: "ltr" };

const PREFIX = "/en";

export function localeFromPath(path: string): Locale {
  return path === PREFIX || path.startsWith(`${PREFIX}/`) ? "en" : DEFAULT_LOCALE;
}

/** المسار بلا بادئة اللغة: `/en/about` ← `/about`، و`/en` ← `/`. */
export function stripLocale(path: string): string {
  if (localeFromPath(path) === DEFAULT_LOCALE) return path;
  return path.slice(PREFIX.length) || "/";
}

/** المسار نفسه بلغة أخرى. يقبل مسارًا ببادئة أو بلا بادئة. */
export function localizePath(path: string, locale: Locale): string {
  const bare = stripLocale(path);
  if (locale === DEFAULT_LOCALE) return bare;
  return bare === "/" ? PREFIX : `${PREFIX}${bare}`;
}

/** قيمة معامل المسار `locale` في الموجّه: فارغ للعربية. */
export function localeParam(locale: Locale): string {
  return locale === DEFAULT_LOCALE ? "" : locale;
}

export function otherLocale(locale: Locale): Locale {
  return locale === "ar" ? "en" : "ar";
}
