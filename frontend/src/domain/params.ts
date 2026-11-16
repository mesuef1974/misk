// مخطط معاملات القالب: نسخة الواجهة من قواعد apps/catalog/domain.py.
// الخادم هو الحَكَم؛ هذا الفحص يُظهر الخطأ بجانب الحقل قبل الإرسال فقط.

export type ParamChoice = string | number;

export interface ParamField {
  name: string;
  type: "text" | "int" | "bool" | "choice";
  label?: string;
  required?: boolean;
  max_length?: number;
  min?: number;
  max?: number;
  choices?: ParamChoice[];
}

export type ParamValue = string | number | boolean;
export type ParamValues = Record<string, ParamValue>;

const DEFAULT_TEXT_LENGTH = 200;

export function fieldLabel(field: ParamField): string {
  return field.label || field.name;
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
      if (field.required ?? true) errors[field.name] = "مطلوب";
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
  if (field.type === "text") {
    const limit = field.max_length ?? DEFAULT_TEXT_LENGTH;
    if (typeof value !== "string") return "نص";
    return collapse(value).length > limit ? `أطول من ${limit} حرفًا` : "";
  }
  if (field.type === "int") {
    if (typeof value !== "number" || !Number.isInteger(value)) return "عدد صحيح";
    const below = field.min !== undefined && value < field.min;
    const above = field.max !== undefined && value > field.max;
    return below || above ? "خارج المدى المسموح" : "";
  }
  if (field.type === "bool") return typeof value === "boolean" ? "" : "قيمة منطقية";
  return (field.choices ?? []).includes(value as ParamChoice) ? "" : "ليست من الخيارات";
}
