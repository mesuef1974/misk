// نموذج «طلب جديد»: حالته، وفحصه، وتحويله إلى ما يرسله الخادم. منطق خالص يُختبر بلا واجهة.
import { cleanParams, emptyParams, type ParamField, type ParamValues } from "@/domain/params";
import { i18n } from "@/i18n";
import type { OrderDraft, OrderItemDraft } from "@/services/orders";

/** حقول الأرقام تحمل "" حين تُترك فارغة، كما يعطيها حقل الإدخال. */
export interface ItemForm {
  key: number;
  templateSlug: string;
  materialId: number | "";
  params: ParamValues;
  quantity: number | "";
  unitPrice: number | "";
}

export interface OrderForm {
  customerName: string;
  occasionDate: string;
  notes: string;
  items: ItemForm[];
}

export interface TemplateInfo {
  slug: string;
  param_schema: ParamField[];
  base_price: string;
}

/** أخطاء البند بمفتاح الحقل؛ حقول المعاملات مفتاحها `param:<الاسم>`. */
export type ItemErrors = Record<string, string>;

export interface FormErrors {
  customerName?: string;
  items: Record<number, ItemErrors>;
}

export function newItem(key: number): ItemForm {
  return { key, templateSlug: "", materialId: "", params: {}, quantity: 1, unitPrice: "" };
}

/** تغيير القالب يبدأ معاملاته من جديد: مخطط القالب السابق لا يصلح للجديد. */
export function withTemplate(item: ItemForm, template: TemplateInfo | undefined): ItemForm {
  return { ...item, templateSlug: template?.slug ?? "", params: emptyParams(template?.param_schema ?? []) };
}

export function hasErrors(errors: FormErrors): boolean {
  return Boolean(errors.customerName) || Object.keys(errors.items).length > 0;
}

export function buildDraft(
  form: OrderForm,
  clientRef: string,
  templates: TemplateInfo[],
): { draft: OrderDraft | null; errors: FormErrors } {
  // رسائل الفحص بلغة الصفحة لحظة الحفظ.
  const { t } = i18n.global;
  const errors: FormErrors = { items: {} };
  const customerName = form.customerName.split(/\s+/).filter(Boolean).join(" ");
  if (!customerName) errors.customerName = t("orders.validation.customerRequired");

  const items: OrderItemDraft[] = [];
  for (const item of form.items) {
    const itemErrors: ItemErrors = {};
    const template = templates.find((candidate) => candidate.slug === item.templateSlug);
    if (!template) itemErrors.template = t("orders.validation.chooseTemplate");
    if (item.materialId === "") itemErrors.material = t("orders.validation.chooseMaterial");
    if (item.quantity === "" || !Number.isInteger(item.quantity) || item.quantity < 1) {
      itemErrors.quantity = t("orders.validation.quantity");
    }
    if (item.unitPrice !== "" && !(item.unitPrice >= 0)) itemErrors.unitPrice = t("orders.validation.negativePrice");
    const cleaned = cleanParams(template?.param_schema ?? [], item.params);
    for (const [name, message] of Object.entries(cleaned.errors)) itemErrors[`param:${name}`] = message;

    if (Object.keys(itemErrors).length > 0) {
      errors.items[item.key] = itemErrors;
    } else {
      items.push({
        template_slug: item.templateSlug,
        material_id: item.materialId as number,
        params: cleaned.params,
        quantity: item.quantity as number,
        unit_price: item.unitPrice === "" ? null : String(item.unitPrice),
      });
    }
  }

  if (hasErrors(errors)) return { draft: null, errors };
  return {
    draft: {
      client_ref: clientRef,
      customer_name: customerName,
      occasion_date: form.occasionDate || null,
      notes: form.notes.trim(),
      items,
    },
    errors,
  };
}

/** تقدير للعرض فقط؛ المجموع المعتمد يحسبه الخادم. السعر الفارغ يأخذ سعر القالب الأساسي. */
export function estimateTotal(items: ItemForm[], templates: TemplateInfo[]): number {
  return items.reduce((sum, item) => {
    const base = templates.find((candidate) => candidate.slug === item.templateSlug)?.base_price ?? 0;
    const price = item.unitPrice === "" ? Number(base) : item.unitPrice;
    return sum + (Number(item.quantity) || 0) * (Number(price) || 0);
  }, 0);
}
