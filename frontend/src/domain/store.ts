// منطق المتجر الخالص: قراءة أخطاء الخادم، حدود الحروف، قيم البدء، وتنسيق المواعيد. يُختبر بلا واجهة.
import { ApiError } from "@/api/client";
import type { Locale } from "@/domain/locale";
import type { ParamField, ParamValue, ParamValues } from "@/domain/params";
import { currentLocale, i18n } from "@/i18n";
import type { FieldLimit } from "@/services/store";

/** الاسم بلغة الصفحة: الإنجليزي في الصفحة الإنجليزية إن أُدخل، وإلا العربي. */
export function localized(arabic: string, english: string, locale: Locale = currentLocale()): string {
  return (locale === "en" && english) || arabic;
}

/** اسم البند كما يُعرض في السلة والتتبّع: نسخة التصميم الجاهز المسمّاة تُذكر برمزها. */
export function lineName(item: { name: string; name_en: string; variant_code?: string }): string {
  const name = localized(item.name, item.name_en);
  return item.variant_code ? i18n.global.t("store.design.named", { name, code: item.variant_code }) : name;
}

/** خطأ مسارات المتجر: رمز ثابت، ورسالة بلغة الطلب، وأخطاء الحقول، وقوالب مقترحة، وأقرب جاهزية. */
export interface StoreError {
  code: string;
  message: string;
  fields: Record<string, string>;
  suggestions: string[];
  readyOn: string | null;
}

interface ErrorBody {
  code?: unknown;
  fields?: unknown;
  suggestions?: unknown;
  ready_on?: unknown;
}

/** يقرأ جسم الخطأ دون أن يثق بشكله: رد من وسيط أو عطل (HTML، 502) يعود بلا رمز ولا حقول. */
export function storeError(error: unknown, fallback: string): StoreError {
  const blank: StoreError = { code: "", message: fallback, fields: {}, suggestions: [], readyOn: null };
  if (!(error instanceof ApiError)) return blank;
  const body = (error.body && typeof error.body === "object" ? error.body : {}) as ErrorBody;
  const fields: Record<string, string> = {};
  if (body.fields && typeof body.fields === "object") {
    for (const [name, value] of Object.entries(body.fields as Record<string, unknown>)) {
      const message = (value as { message?: unknown } | null)?.message;
      if (typeof message === "string") fields[name] = message;
    }
  }
  return {
    code: typeof body.code === "string" ? body.code : "",
    message: error.message,
    fields,
    suggestions: Array.isArray(body.suggestions) ? body.suggestions.filter((item) => typeof item === "string") : [],
    readyOn: typeof body.ready_on === "string" ? body.ready_on : null,
  };
}

/** قيم بدء المصمِّم: حقل الاختيار المطلوب يأخذ أول خياراته فتُرسم المعاينة من أول حرف يكتبه العميل. */
export function initialParams(schema: ParamField[]): ParamValues {
  return Object.fromEntries(
    schema.map((field): [string, ParamValue] => {
      if (field.type === "bool") return [field.name, false];
      if (field.type === "choice" && (field.required ?? true) && field.choices?.length) return [field.name, field.choices[0]];
      return [field.name, ""];
    }),
  );
}

/** حدّ الحقل عند قيم الاختيار الجارية: الصف الذي يطابق كل ما في `when`. */
export function limitFor(limits: FieldLimit[], field: string, params: ParamValues): FieldLimit | undefined {
  return limits.find(
    (limit) => limit.field === field && Object.entries(limit.when).every(([name, value]) => params[name] === value),
  );
}

/** عدد الحروف كما يعدّه الخادم: بعد طيّ الفراغات. */
export function textLength(value: ParamValue | undefined): number {
  return typeof value === "string" ? value.split(/\s+/).filter(Boolean).join(" ").length : 0;
}

/** ملف القص صورةً: يُعرض في <img> فلا يُنفَّذ فيه سكربت ولا يُحمَّل منه مورد، مهما كان مصدره. */
export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// الأرقام لاتينية في اللغتين؛ اسم اليوم والشهر بلغة الصفحة (القاعدة نفسها في domain/orders.ts).
const INTL: Record<Locale, string> = { ar: "ar-u-nu-latn-ca-gregory", en: "en-GB" };
const formats = new Map<string, Intl.DateTimeFormat>();

function format(kind: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${currentLocale()}:${kind}`;
  let cached = formats.get(key);
  if (!cached) {
    cached = new Intl.DateTimeFormat(INTL[currentLocale()], options);
    formats.set(key, cached);
  }
  return cached;
}

/** يوم ISO (YYYY-MM-DD) باسمه: «السبت، 28 نوفمبر». يُقرأ محليًّا كي لا يزيحه فرق التوقيت يومًا. */
export function formatDay(iso: string): string {
  const [year, month, dayOfMonth] = iso.split("-").map(Number);
  return format("day", { weekday: "long", day: "numeric", month: "long" }).format(new Date(year, month - 1, dayOfMonth));
}

/** ساعة لحظة ISO بتوقيت المتصفح: «4:30 م». */
export function formatTime(iso: string): string {
  const instant = new Date(iso);
  return Number.isNaN(instant.getTime()) ? "" : format("time", { hour: "numeric", minute: "2-digit" }).format(instant);
}

/** لحظة ISO بيومها وساعتها. */
export function formatMoment(iso: string): string {
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return "";
  return format("moment", { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" }).format(instant);
}

/** رابط الدفع الذي يعيده الخادم: مسار داخل الموقع أو صفحة https عند البوابة، ولا شيء غيرهما. */
export function safePaymentUrl(url: string | null | undefined): string {
  if (!url) return "";
  if (url.startsWith("/") && !url.startsWith("//") && !url.includes("\\")) return url;
  return /^https:\/\//i.test(url) ? url : "";
}
