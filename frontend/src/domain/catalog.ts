// نماذج الكتالوج: حالتها، وفحصها، وتحويلها إلى ما يرسله الخادم. منطق خالص يُختبر بلا واجهة.
// الحدود نسخة الواجهة من حقول apps/catalog/models.py؛ الخادم هو الحَكَم.
import type { ParamChoice, ParamField } from "@/domain/params";
import type {
  CalibrationDraft,
  Material,
  MaterialDraft,
  ProductTemplate,
  TemplateDraft,
} from "@/services/catalog";

export const MATERIAL_KINDS = ["leather", "wood", "acrylic", "paper", "other"] as const;
const KIND_LABELS: Record<string, string> = {
  leather: "جلد نباتي الدباغة",
  wood: "خشب",
  acrylic: "أكريليك",
  paper: "ورق مقوّى",
  other: "أخرى",
};

export const OPERATIONS = ["engrave", "score", "cut"] as const;
const OPERATION_LABELS: Record<string, string> = { engrave: "حفر", score: "خط", cut: "قص" };

export const FIELD_TYPES = ["text", "int", "bool", "choice"] as const;
export const FIELD_TYPE_LABELS: Record<ParamField["type"], string> = {
  text: "نص",
  int: "عدد صحيح",
  bool: "نعم/لا",
  choice: "اختيار من قائمة",
};

/** أيقونة الهوية لنوع المادة (brand/misk/identity/icons)؛ ما لا أيقونة له في الهوية يبقى بلا أيقونة. */
export const KIND_ICONS: Record<string, string> = { leather: "leather", wood: "wood", acrylic: "acrylic" };

/** أيقونة الهوية لمولّد القالب: الكفرات والتوزيعات لها أيقونتاهما، وما عداهما قطعة اسم. */
export const GENERATOR_ICONS: Record<string, string> = { case_name: "phone-case", arched_card: "giveaways", jar_lid: "giveaways" };

export function templateIcon(generator: string): string {
  return GENERATOR_ICONS[generator] ?? "name";
}

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export function operationLabel(operation: string): string {
  return OPERATION_LABELS[operation] ?? operation;
}

export type Errors = Record<string, string>;
type NumberInput = number | "";

function collapse(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

/** عدد عشري داخل المدى وبخانات عشرية لا تزيد على `places`، كما يقبله DecimalField. */
function decimalError(value: NumberInput, min: number, max: number, places: number): string {
  if (value === "" || !Number.isFinite(value)) return "مطلوب";
  if (value < min || value > max) return `بين ${min} و${max}`;
  const scaled = value * 10 ** places;
  return Math.abs(scaled - Math.round(scaled)) > 1e-6 ? `${places} خانات عشرية على الأكثر` : "";
}

function integerError(value: NumberInput, min: number, max: number): string {
  if (value === "") return "مطلوب";
  return Number.isInteger(value) && value >= min && value <= max ? "" : `عدد صحيح بين ${min} و${max}`;
}

function put(errors: Errors, key: string, message: string): void {
  if (message) errors[key] = message;
}

// ——— المادة ———

export interface MaterialForm {
  name: string;
  kind: string;
  thickness: NumberInput;
  sheetCost: NumberInput;
  supplier: string;
  notes: string;
}

export function emptyMaterialForm(): MaterialForm {
  return { name: "", kind: "", thickness: "", sheetCost: 0, supplier: "", notes: "" };
}

export function materialFormFrom(material: Material): MaterialForm {
  return {
    name: material.name,
    kind: material.kind,
    thickness: Number(material.thickness_mm),
    sheetCost: Number(material.sheet_cost),
    supplier: material.supplier,
    notes: material.notes,
  };
}

export function buildMaterialDraft(form: MaterialForm): { draft: MaterialDraft | null; errors: Errors } {
  const errors: Errors = {};
  const name = collapse(form.name);
  if (!name) errors.name = "اسم المادة مطلوب";
  else if (name.length > 120) errors.name = "أطول من 120 حرفًا";
  if (!(MATERIAL_KINDS as readonly string[]).includes(form.kind)) errors.kind = "اختر النوع";
  put(errors, "thickness", decimalError(form.thickness, 0.1, 999.99, 2));
  put(errors, "sheetCost", decimalError(form.sheetCost, 0, 999999.99, 2));
  if (form.supplier.trim().length > 160) errors.supplier = "أطول من 160 حرفًا";
  if (Object.keys(errors).length > 0) return { draft: null, errors };
  return {
    draft: {
      name,
      kind: form.kind,
      thickness_mm: String(form.thickness),
      sheet_cost: String(form.sheetCost),
      supplier: form.supplier.trim(),
      notes: form.notes.trim(),
    },
    errors,
  };
}

// ——— المعايرة ———

export interface CalibrationForm {
  operation: string;
  power: NumberInput;
  speed: NumberInput;
  passes: NumberInput;
  linesPerCm: NumberInput;
  minLine: NumberInput;
  measuredOn: string;
  notes: string;
}

/** تاريخ اليوم بالتوقيت المحلي (YYYY-MM-DD)؛ toISOString يعطي يوم UTC فيسبق أو يتأخر قرب منتصف الليل. */
export function localToday(now: Date = new Date()): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function emptyCalibrationForm(today: string = localToday()): CalibrationForm {
  return {
    operation: "",
    power: "",
    speed: "",
    passes: 1,
    linesPerCm: "",
    minLine: "",
    measuredOn: today,
    notes: "",
  };
}

export function buildCalibrationDraft(form: CalibrationForm): {
  draft: CalibrationDraft | null;
  errors: Errors;
} {
  const errors: Errors = {};
  if (!(OPERATIONS as readonly string[]).includes(form.operation)) errors.operation = "اختر العملية";
  put(errors, "power", integerError(form.power, 1, 100));
  put(errors, "speed", decimalError(form.speed, 0.1, 99999.9, 1));
  put(errors, "passes", integerError(form.passes, 1, 99));
  if (form.linesPerCm !== "") put(errors, "linesPerCm", integerError(form.linesPerCm, 1, 9999));
  put(errors, "minLine", decimalError(form.minLine, 0.01, 99.99, 2));
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.measuredOn)) errors.measuredOn = "تاريخ القياس مطلوب";
  if (Object.keys(errors).length > 0) return { draft: null, errors };
  return {
    draft: {
      operation: form.operation,
      power_pct: form.power as number,
      speed_mm_s: String(form.speed),
      min_line_mm: String(form.minLine),
      measured_on: form.measuredOn,
      passes: form.passes as number,
      lines_per_cm: form.linesPerCm === "" ? null : form.linesPerCm,
      notes: form.notes.trim(),
    },
    errors,
  };
}

// ——— القالب ومخطط معاملاته ———

export interface SchemaFieldForm {
  key: number;
  name: string;
  label: string;
  type: ParamField["type"];
  required: boolean;
  maxLength: NumberInput;
  min: NumberInput;
  max: NumberInput;
  /** الخيارات نصًّا، كل خيار في سطر أو بينها فاصلة. */
  choices: string;
}

export interface TemplateForm {
  slug: string;
  name: string;
  generator: string;
  width: NumberInput;
  height: NumberInput;
  basePrice: NumberInput;
  fields: SchemaFieldForm[];
}

export function newSchemaField(key: number): SchemaFieldForm {
  return { key, name: "", label: "", type: "text", required: true, maxLength: "", min: "", max: "", choices: "" };
}

export function emptyTemplateForm(): TemplateForm {
  return { slug: "", name: "", generator: "", width: "", height: "", basePrice: 0, fields: [] };
}

export function templateFormFrom(template: ProductTemplate): TemplateForm {
  return {
    slug: template.slug,
    name: template.name,
    generator: template.generator,
    width: Number(template.width_mm),
    height: Number(template.height_mm),
    basePrice: Number(template.base_price),
    fields: template.param_schema.map((field, index) => ({
      key: index + 1,
      name: field.name,
      label: field.label ?? "",
      type: field.type,
      required: field.required ?? true,
      maxLength: field.max_length ?? "",
      min: field.min ?? "",
      max: field.max ?? "",
      choices: (field.choices ?? []).join("\n"),
    })),
  };
}

export function parseChoices(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(/[\n,،]/)) {
    const choice = collapse(part);
    if (choice) seen.add(choice);
  }
  return [...seen];
}

/**
 * الخيارات الرقمية تبقى أرقامًا إن كانت كذلك في القالب الأصلي: تحويلها إلى نصوص عند التعديل
 * يُبطل قيم الطلبات المحفوظة بها.
 */
function keepChoiceTypes(choices: string[], original: ParamChoice[] | undefined): ParamChoice[] {
  const numeric = new Set((original ?? []).filter((choice) => typeof choice === "number").map(String));
  return choices.map((choice) => (numeric.has(choice) ? Number(choice) : choice));
}

function buildField(
  form: SchemaFieldForm,
  original: ParamField | undefined,
): { field: ParamField | null; error: string } {
  const name = form.name.trim();
  if (!name) return { field: null, error: "اسم الحقل مطلوب" };
  const field: ParamField = { name, type: form.type };
  const label = collapse(form.label);
  if (label) field.label = label;
  if (!form.required) field.required = false;
  if (form.type === "text" && form.maxLength !== "") {
    if (!Number.isInteger(form.maxLength) || form.maxLength < 1) {
      return { field: null, error: "أقصى طول عدد صحيح موجب" };
    }
    field.max_length = form.maxLength;
  }
  if (form.type === "int") {
    for (const bound of [form.min, form.max]) {
      if (bound !== "" && !Number.isInteger(bound)) return { field: null, error: "الحدّان عددان صحيحان" };
    }
    if (form.min !== "" && form.max !== "" && form.min > form.max) {
      return { field: null, error: "الحد الأدنى أكبر من الأقصى" };
    }
    if (form.min !== "") field.min = form.min;
    if (form.max !== "") field.max = form.max;
  }
  if (form.type === "choice") {
    const choices = parseChoices(form.choices);
    if (choices.length === 0) return { field: null, error: "أدخل خيارًا واحدًا على الأقل" };
    field.choices = keepChoiceTypes(choices, original?.type === "choice" ? original.choices : undefined);
  }
  return { field, error: "" };
}

/** أخطاء حقول المخطط مفتاحها `field:<key>`. `original` القالب قبل التعديل إن وُجد. */
export function buildTemplateDraft(
  form: TemplateForm,
  original?: ProductTemplate,
): { draft: TemplateDraft | null; errors: Errors } {
  const errors: Errors = {};
  const slug = form.slug.trim();
  if (!slug) errors.slug = "المعرّف مطلوب";
  else if (slug.length > 64 || !/^[\p{L}\p{N}_-]+$/u.test(slug)) {
    errors.slug = "حروف وأرقام وشرطات فقط، بلا مسافات، و64 على الأكثر";
  }
  const name = collapse(form.name);
  if (!name) errors.name = "اسم القالب مطلوب";
  else if (name.length > 120) errors.name = "أطول من 120 حرفًا";
  const generator = form.generator.trim();
  if (!generator) errors.generator = "مفتاح المولّد مطلوب";
  else if (generator.length > 64) errors.generator = "أطول من 64 حرفًا";
  put(errors, "width", decimalError(form.width, 1, 99999.9, 1));
  put(errors, "height", decimalError(form.height, 1, 99999.9, 1));
  put(errors, "basePrice", decimalError(form.basePrice, 0, 999999.99, 2));

  const schema: ParamField[] = [];
  const names = new Set<string>();
  for (const fieldForm of form.fields) {
    const before = original?.param_schema.find((field) => field.name === fieldForm.name.trim());
    const { field, error } = buildField(fieldForm, before);
    if (!field) errors[`field:${fieldForm.key}`] = error;
    else if (names.has(field.name)) errors[`field:${fieldForm.key}`] = `الاسم ${field.name} مكرر`;
    else {
      names.add(field.name);
      schema.push(field);
    }
  }

  if (Object.keys(errors).length > 0) return { draft: null, errors };
  return {
    draft: {
      slug,
      name,
      generator,
      width_mm: String(form.width),
      height_mm: String(form.height),
      param_schema: schema,
      base_price: String(form.basePrice),
    },
    errors,
  };
}

/** وصف موجز لحقل المخطط في قائمة القوالب. */
export function describeField(field: ParamField): string {
  const label = field.label || field.name;
  const optional = field.required === false ? "، اختياري" : "";
  return `${label} (${FIELD_TYPE_LABELS[field.type]}${optional})`;
}
