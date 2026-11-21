import { createI18n } from "vue-i18n";
import { DEFAULT_LOCALE, DIRECTIONS, type Locale } from "@/domain/locale";
import ar from "./locales/ar";

export type Messages = typeof ar;

// العربية في الحزمة الأولى (اللغة الافتراضية ولغة الرجوع)؛ الإنجليزية تُحمَّل عند أول مسار `/en` (Lazy loading).
const LOADERS: Partial<Record<Locale, () => Promise<{ default: Messages }>>> = {
  en: () => import("./locales/en"),
};

export const i18n = createI18n({
  legacy: false,
  locale: DEFAULT_LOCALE as Locale,
  fallbackLocale: DEFAULT_LOCALE,
  messages: { ar } as Record<Locale, Messages>,
});

export function currentLocale(): Locale {
  return i18n.global.locale.value;
}

/** يحمّل رسائل اللغة إن لم تكن محمَّلة ثم يجعلها لغة الواجهة ولغة المستند واتجاهه. */
export async function setLocale(locale: Locale): Promise<void> {
  const load = LOADERS[locale];
  if (load && !i18n.global.availableLocales.includes(locale)) {
    i18n.global.setLocaleMessage(locale, (await load()).default);
  }
  i18n.global.locale.value = locale;
  const root = document.documentElement;
  root.lang = locale;
  root.dir = DIRECTIONS[locale];
}
