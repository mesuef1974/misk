// مخطط معاملات القالب: نسخة الواجهة من قواعد apps/catalog/domain.py.
// الخادم هو الحَكَم؛ هذا الفحص يُظهر الخطأ بجانب الحقل قبل الإرسال فقط.

import { currentLocale, i18n } from "@/i18n";

export type ParamChoice = string | number;

export interface ParamField {
  name: string;
  type: "text" | "int" | "bool" | "choice";
  label?: string;
  /** التسمية في الصفحات الإنجليزية؛ غيابها يعرض العربية. */
  label_en?: string;
  required?: boolean;
  max_length?: number;
  min?: number;
  max?: number;
  choices?: ParamChoice[];
  /** تسميات الخيارات الإنجليزية، تقابل `choices` موضعًا بموضع؛ القيمة المحفوظة هي الخيار نفسه. */
  choices_en?: string[];
}

export type ParamValue = string | number | boolean;
export type ParamValues = Record<string, ParamValue>;

const DEFAULT_TEXT_LENGTH = 200;

export function fieldLabel(field: ParamField): string {
  return (currentLocale() === "en" && field.label_en) || field.label || field.name;
}

/** نص الخيار بلغة الصفحة؛ قيمة ليست من خيارات الحقل (نص حر أو خيار حُذف) تُعرض كما هي. */
export function choiceLabel(field: Pick<ParamField, "choices" | "choices_en">, value: ParamValue): string {
  const index = (field.choices ?? []).indexOf(value as ParamChoice);
  return (currentLocale() === "en" && field.choices_en?.[index]) || String(value);
}

/** قيم البدء لنموذج فارغ: المنطقي false، وغيره نص فارغ يعني «لم يُملأ». */
export function emptyParams(schema: ParamField[]): ParamValues {
  return Object.fromEntries(schema.map((field) => [field.name, field.type === "bool" ? false : ""]));
}

export interface CleanResult {
  params: ParamValues;
  errors: Record<string, string>;
}

export function cleanParams(schema: ParamField[], raw: ParamValues): CleanResult {
  const params: ParamValues = {};
  const errors: Record<string, string> = {};
  for (const field of schema) {
    const value = raw[field.name];
    if (value === undefined || value === "") {
      if (field.required ?? true) errors[field.name] = i18n.global.t("orders.validation.required");
      continue;
    }
    const error = check(field, value);
    if (error) errors[field.name] = error;
    else params[field.name] = typeof value === "string" ? collapse(value) : value;
  }
  return { params, errors };
}

function collapse(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

function check(field: ParamField, value: ParamValue): string {
  const { t } = i18n.global;
  if (field.type === "text") {
    const limit = field.max_length ?? DEFAULT_TEXT_LENGTH;
    if (typeof value !== "string") return t("orders.validation.text");
    return collapse(value).length > limit ? t("orders.validation.tooLong", { limit }) : "";
  }
  if (field.type === "int") {
    if (typeof value !== "number" || !Number.isInteger(value)) return t("orders.validation.integer");
    const below = field.min !== undefined && value < field.min;
    const above = field.max !== undefined && value > field.max;
    return below || above ? t("orders.validation.outOfRange") : "";
  }
  if (field.type === "bool") return typeof value === "boolean" ? "" : t("orders.validation.boolean");
  return (field.choices ?? []).includes(value as ParamChoice) ? "" : t("orders.validation.notAChoice");
}
