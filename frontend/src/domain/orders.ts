// حالات الطلب وتسمياتها. الانتقالات المتاحة تأتي من الخادم في `Order.next_statuses`
// (تتبع قناة الطلب وطريقة استلامه)، فلا نسخة ثانية لها هنا.

import type { Locale } from "@/domain/locale";
import { currentLocale, i18n } from "@/i18n";

export const ORDER_STATUSES = [
  "draft",
  "awaiting_payment",
  "paid",
  "under_review",
  "confirmed",
  "in_production",
  "ready",
  "out_for_delivery",
  "ready_for_pickup",
  "delivered",
  "cancelled",
  "refunded",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

/** حالات طلب الطاقم: تظهر في التصفية دائمًا. حالات المتجر تظهر حين يكون فيها طلب. */
export const WORKSHOP_STATUSES: readonly OrderStatus[] = [
  "draft",
  "confirmed",
  "in_production",
  "ready",
  "delivered",
  "cancelled",
];

/** الحالات التي لها زر ينقل الطلب إليها. غيرها يدخله النظام وحده (الدفع والاسترداد). */
const ACTIONABLE: ReadonlySet<OrderStatus> = new Set([
  "under_review",
  "confirmed",
  "in_production",
  "ready",
  "out_for_delivery",
  "ready_for_pickup",
  "delivered",
  "cancelled",
]);

function isStatus(status: string): status is OrderStatus {
  return (ORDER_STATUSES as readonly string[]).includes(status);
}

export function statusLabel(status: string): string {
  return isStatus(status) ? i18n.global.t(`orderStatus.${status}`) : status;
}

/** نص الزر الذي ينقل الطلب إلى الحالة. */
export function transitionAction(status: OrderStatus): string {
  return ACTIONABLE.has(status) ? i18n.global.t(`orderAction.${status}` as "orderAction.confirmed") : "";
}

/** أزرار الطلب: ما أتاحه الخادم مما تعرفه الواجهة وله زر. */
export function orderActions(order: { next_statuses: readonly string[] }): OrderStatus[] {
  return order.next_statuses.filter(isStatus).filter((status) => ACTIONABLE.has(status));
}

// الأرقام لاتينية في اللغتين؛ اسم الشهر والعملة بلغة الصفحة.
const INTL: Record<Locale, string> = { ar: "ar-u-nu-latn-ca-gregory", en: "en-GB" };
const moneyFormats = new Map<Locale, Intl.NumberFormat>();
const dayFormats = new Map<Locale, Intl.DateTimeFormat>();

function money(): Intl.NumberFormat {
  const locale = currentLocale();
  let format = moneyFormats.get(locale);
  if (!format) {
    format = new Intl.NumberFormat(INTL[locale], { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    moneyFormats.set(locale, format);
  }
  return format;
}

function day(): Intl.DateTimeFormat {
  const locale = currentLocale();
  let format = dayFormats.get(locale);
  if (!format) {
    format = new Intl.DateTimeFormat(INTL[locale], { dateStyle: "medium" });
    dayFormats.set(locale, format);
  }
  return format;
}

export function currency(): string {
  return i18n.global.t("currency");
}

export function formatMoney(amount: string | number): string {
  const value = Number(amount);
  return `${money().format(Number.isFinite(value) ? value : 0)} ${currency()}`;
}

/** تاريخ ISO بلا وقت (YYYY-MM-DD)؛ يُقرأ محليًّا كي لا يزيحه فرق التوقيت يومًا. */
export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [year, month, dayOfMonth] = iso.split("-").map(Number);
  return day().format(new Date(year, month - 1, dayOfMonth));
}

/** تاريخ لحظة ISO (بمنطقتها الزمنية) كما يراه المستخدم محليًّا. */
export function formatInstant(iso: string): string {
  const instant = new Date(iso);
  return Number.isNaN(instant.getTime()) ? "" : day().format(instant);
}

export function lineTotal(quantity: number, unitPrice: string | number): number {
  return quantity * Number(unitPrice);
}
