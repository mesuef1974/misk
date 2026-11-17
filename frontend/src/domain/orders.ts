// حالات الطلب وانتقالاتها: نسخة الواجهة من TRANSITIONS في apps/orders/services.py.
// تُستعمل لإظهار الأزرار المتاحة فقط؛ الخادم يرفض أي انتقال غير مسموح.

export const ORDER_STATUSES = ["draft", "confirmed", "in_production", "ready", "delivered", "cancelled"] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const STATUS_LABELS: Record<OrderStatus, string> = {
  draft: "مسودة",
  confirmed: "مؤكَّد",
  in_production: "قيد التنفيذ",
  ready: "جاهز",
  delivered: "مُسلَّم",
  cancelled: "ملغى",
};

const TRANSITIONS: Record<OrderStatus, readonly OrderStatus[]> = {
  draft: ["confirmed", "cancelled"],
  confirmed: ["in_production", "cancelled"],
  in_production: ["ready", "cancelled"],
  ready: ["delivered"],
  delivered: [],
  cancelled: [],
};

/** نص الزر الذي ينقل الطلب إلى الحالة. */
export const TRANSITION_ACTIONS: Record<OrderStatus, string> = {
  draft: "",
  confirmed: "تأكيد الطلب",
  in_production: "بدء التنفيذ",
  ready: "جاهز للتسليم",
  delivered: "تسليم للعميل",
  cancelled: "إلغاء الطلب",
};

function isStatus(status: string): status is OrderStatus {
  return (ORDER_STATUSES as readonly string[]).includes(status);
}

export function statusLabel(status: string): string {
  return isStatus(status) ? STATUS_LABELS[status] : status;
}

export function nextStatuses(status: string): readonly OrderStatus[] {
  return isStatus(status) ? TRANSITIONS[status] : [];
}

const money = new Intl.NumberFormat("ar-u-nu-latn", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const day = new Intl.DateTimeFormat("ar-u-nu-latn-ca-gregory", { dateStyle: "medium" });

export const CURRENCY = "ر.ق";

export function formatMoney(amount: string | number): string {
  const value = Number(amount);
  return `${money.format(Number.isFinite(value) ? value : 0)} ${CURRENCY}`;
}

/** تاريخ ISO بلا وقت (YYYY-MM-DD)؛ يُقرأ محليًّا كي لا يزيحه فرق التوقيت يومًا. */
export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [year, month, dayOfMonth] = iso.split("-").map(Number);
  return day.format(new Date(year, month - 1, dayOfMonth));
}

/** تاريخ لحظة ISO (بمنطقتها الزمنية) كما يراه المستخدم محليًّا. */
export function formatInstant(iso: string): string {
  const instant = new Date(iso);
  return Number.isNaN(instant.getTime()) ? "" : day.format(instant);
}

export function lineTotal(quantity: number, unitPrice: string | number): number {
  return quantity * Number(unitPrice);
}
