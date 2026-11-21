// حالات الطلب وتسمياتها. الانتقالات المتاحة تأتي من الخادم في `Order.next_statuses`
// (تتبع قناة الطلب وطريقة استلامه)، فلا نسخة ثانية لها هنا.

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

export const STATUS_LABELS: Record<OrderStatus, string> = {
  draft: "مسودة",
  awaiting_payment: "بانتظار الدفع",
  paid: "مدفوع",
  under_review: "قيد المراجعة",
  confirmed: "مؤكَّد",
  in_production: "قيد التنفيذ",
  ready: "جاهز",
  out_for_delivery: "في الطريق",
  ready_for_pickup: "جاهز للاستلام",
  delivered: "مُسلَّم",
  cancelled: "ملغى",
  refunded: "مُستردّ",
};

/** نص الزر الذي ينقل الطلب إلى الحالة. الفارغ حالة يدخلها النظام وحده (الدفع والاسترداد). */
export const TRANSITION_ACTIONS: Record<OrderStatus, string> = {
  draft: "",
  awaiting_payment: "",
  paid: "",
  under_review: "تحويل للمراجعة",
  confirmed: "تأكيد الطلب",
  in_production: "بدء التنفيذ",
  ready: "جاهز للتسليم",
  out_for_delivery: "خرج للتوصيل",
  ready_for_pickup: "جاهز للاستلام",
  delivered: "تسليم للعميل",
  cancelled: "إلغاء الطلب",
  refunded: "",
};

function isStatus(status: string): status is OrderStatus {
  return (ORDER_STATUSES as readonly string[]).includes(status);
}

export function statusLabel(status: string): string {
  return isStatus(status) ? STATUS_LABELS[status] : status;
}

/** أزرار الطلب: ما أتاحه الخادم مما تعرفه الواجهة وله زر. */
export function orderActions(order: { next_statuses: readonly string[] }): OrderStatus[] {
  return order.next_statuses.filter(isStatus).filter((status) => TRANSITION_ACTIONS[status] !== "");
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
