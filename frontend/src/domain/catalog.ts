// نماذج الكتالوج: حالتها، وفحصها، وتحويلها إلى ما يرسله الخادم. منطق خالص يُختبر بلا واجهة.
// الحدود نسخة الواجهة من حقول apps/catalog/models.py؛ الخادم هو الحَكَم.
import { fieldLabel, type ParamChoice, type ParamField } from "@/domain/params";
import { currentLocale, i18n } from "@/i18n";
import type {
  CalibrationDraft,
  Material,
  MaterialDraft,
  ProductTemplate,
  TemplateDraft,
} from "@/services/catalog";

/** اسم القالب بلغة الصفحة: الإنجليزي في الصفحة الإنجليزية إن أُدخل، وإلا العربي. */
export function templateName(template: Pick<ProductTemplate, "name" | "name_en">): string {
  return (currentLocale() === "en" && template.name_en) || template.name;
}

/** اسم المادة بلغة الصفحة، بالقاعدة نفسها. */
export function materialName(material: Pick<Material, "name" | "name_en">): string {
  return (currentLocale() === "en" && material.name_en) || material.name;
}

export const MATERIAL_KINDS = ["leather", "wood", "acrylic", "paper", "other"] as const;

export const OPERATIONS = ["engrave", "score", "cut"] as const;

export const FIELD_TYPES = ["text", "int", "bool", "choice"] as const;

// التسميات دوال تُستدعى وقت العرض: نصها يتبع لغة الصفحة.
export function fieldTypeLabel(type: ParamField["type"]): string {
  return i18n.global.t(`catalog.fieldTypes.${type}`);
}

/** أيقونة الهوية لنوع المادة (brand/misk/identity/icons)؛ ما لا أيقونة له في الهوية يبقى بلا أيقونة. */
export const KIND_ICONS: Record<string, string> = { leather: "leather", wood: "wood", acrylic: "acrylic" };

/** أيقونة الهوية لمولّد القالب: الكفرات والتوزيعات لها أيقونتاهما، وما عداهما قطعة اسم. */
export const GENERATOR_ICONS: Record<string, string> = { case_name: "phone-case", arched_card: "favors", jar_lid: "favors" };

export function templateIcon(generator: string): string {
  return GENERATOR_ICONS[generator] ?? "name";
}

export function kindLabel(kind: string): string {
  return (MATERIAL_KINDS as readonly string[]).includes(kind) ? i18n.global.t(`catalog.kinds.${kind}`) : kind;
}

export function operationLabel(operation: string): string {
  return (OPERATIONS as readonly string[]).includes(operation) ? i18n.global.t(`catalog.operations.${operation}`) : operation;
}

export type Errors = Record<string, string>;

function message(key: string, named: Record<string, unknown> = {}): string {
  return i18n.global.t(`catalog.validation.${key}`, named);
}
type NumberInput = number | "";

function collapse(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

/** عدد عشري داخل المدى وبخانات عشرية لا تزيد على `places`، كما يقبله DecimalField. */
function decimalError(value: NumberInput, min: number, max: number, places: number): string {
  if (value === "" || !Number.isFinite(value)) return message("required");
  if (value < min || value > max) return message("between", { min, max });
  const scaled = value * 10 ** places;
  return Math.abs(scaled - Math.round(scaled)) > 1e-6 ? message("decimalPlaces", { places }) : "";
}

function integerError(value: NumberInput, min: number, max: number): string {
  if (value === "") return message("required");
  return Number.isInteger(value) && value >= min && value <= max ? "" : message("integerBetween", { min, max });
}

function put(errors: Errors, key: string, message: string): void {
  if (message) errors[key] = message;
}

// ——— المادة ———

export interface MaterialForm {
  name: string;
  nameEn: string;
  kind: string;
  thickness: NumberInput;
  sheetCost: NumberInput;
  supplier: string;
  notes: string;
}

export function emptyMaterialForm(): MaterialForm {
  return { name: "", nameEn: "", kind: "", thickness: "", sheetCost: 0, supplier: "", notes: "" };
}

export function materialFormFrom(material: Material): MaterialForm {
  return {
    name: material.name,
    nameEn: material.name_en,
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
  if (!name) errors.name = message("materialName");
  else if (name.length > 120) errors.name = message("longerThan", { max: 120 });
  const nameEn = collapse(form.nameEn);
  if (nameEn.length > 120) errors.nameEn = message("longerThan", { max: 120 });
  if (!(MATERIAL_KINDS as readonly string[]).includes(form.kind)) errors.kind = message("kind");
  put(errors, "thickness", decimalError(form.thickness, 0.1, 999.99, 2));
  put(errors, "sheetCost", decimalError(form.sheetCost, 0, 999999.99, 2));
  if (form.supplier.trim().length > 160) errors.supplier = message("longerThan", { max: 160 });
  if (Object.keys(errors).length > 0) return { draft: null, errors };
  return {
    draft: {
      name,
      name_en: nameEn,
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
  if (!(OPERATIONS as readonly string[]).includes(form.operation)) errors.operation = message("operation");
  put(errors, "power", integerError(form.power, 1, 100));
  put(errors, "speed", decimalError(form.speed, 0.1, 99999.9, 1));
  put(errors, "passes", integerError(form.passes, 1, 99));
  if (form.linesPerCm !== "") put(errors, "linesPerCm", integerError(form.linesPerCm, 1, 9999));
  put(errors, "minLine", decimalError(form.minLine, 0.01, 99.99, 2));
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.measuredOn)) errors.measuredOn = message("measuredOn");
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
  labelEn: string;
  type: ParamField["type"];
  required: boolean;
  maxLength: NumberInput;
  min: NumberInput;
  max: NumberInput;
  /** الخيارات نصًّا، كل خيار في سطر أو بينها فاصلة. */
  choices: string;
  /** تسمياتها الإنجليزية بالترتيب نفسه؛ فارغة تعني عرض الخيارات كما هي. */
  choicesEn: string;
}

export interface TemplateForm {
  slug: string;
  name: string;
  nameEn: string;
  generator: string;
  width: NumberInput;
  height: NumberInput;
  basePrice: NumberInput;
  fields: SchemaFieldForm[];
}

export function newSchemaField(key: number): SchemaFieldForm {
  return {
    key,
    name: "",
    label: "",
    labelEn: "",
    type: "text",
    required: true,
    maxLength: "",
    min: "",
    max: "",
    choices: "",
    choicesEn: "",
  };
}

export function emptyTemplateForm(): TemplateForm {
  return { slug: "", name: "", nameEn: "", generator: "", width: "", height: "", basePrice: 0, fields: [] };
}

export function templateFormFrom(template: ProductTemplate): TemplateForm {
  return {
    slug: template.slug,
    name: template.name,
    nameEn: template.name_en,
    generator: template.generator,
    width: Number(template.width_mm),
    height: Number(template.height_mm),
    basePrice: Number(template.base_price),
    fields: template.param_schema.map((field, index) => ({
      key: index + 1,
      name: field.name,
      label: field.label ?? "",
      labelEn: field.label_en ?? "",
      type: field.type,
      required: field.required ?? true,
      maxLength: field.max_length ?? "",
      min: field.min ?? "",
      max: field.max ?? "",
      choices: (field.choices ?? []).join("\n"),
      choicesEn: (field.choices_en ?? []).join("\n"),
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
  if (!name) return { field: null, error: message("fieldName") };
  const field: ParamField = { name, type: form.type };
  const label = collapse(form.label);
  if (label) field.label = label;
  const labelEn = collapse(form.labelEn);
  if (labelEn) field.label_en = labelEn;
  if (!form.required) field.required = false;
  if (form.type === "text" && form.maxLength !== "") {
    if (!Number.isInteger(form.maxLength) || form.maxLength < 1) {
      return { field: null, error: message("maxLength") };
    }
    field.max_length = form.maxLength;
  }
  if (form.type === "int") {
    for (const bound of [form.min, form.max]) {
      if (bound !== "" && !Number.isInteger(bound)) return { field: null, error: message("integerBounds") };
    }
    if (form.min !== "" && form.max !== "" && form.min > form.max) {
      return { field: null, error: message("minAboveMax") };
    }
    if (form.min !== "") field.min = form.min;
    if (form.max !== "") field.max = form.max;
  }
  if (form.type === "choice") {
    const choices = parseChoices(form.choices);
    if (choices.length === 0) return { field: null, error: message("noChoices") };
    field.choices = keepChoiceTypes(choices, original?.type === "choice" ? original.choices : undefined);
    // التسميات تقابل الخيارات موضعًا بموضع، فلا يُحذف منها مكرر ولا يُقبل عدد مختلف.
    const labels = form.choicesEn.split(/[\n,،]/).map(collapse).filter(Boolean);
    if (labels.length > 0 && labels.length !== choices.length) {
      return { field: null, error: message("choicesEnCount") };
    }
    if (labels.length > 0) field.choices_en = labels;
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
  if (!slug) errors.slug = message("slugRequired");
  else if (slug.length > 64 || !/^[\p{L}\p{N}_-]+$/u.test(slug)) {
    errors.slug = message("slugFormat");
  }
  const name = collapse(form.name);
  if (!name) errors.name = message("templateName");
  else if (name.length > 120) errors.name = message("longerThan", { max: 120 });
  const nameEn = collapse(form.nameEn);
  if (nameEn.length > 120) errors.nameEn = message("longerThan", { max: 120 });
  const generator = form.generator.trim();
  if (!generator) errors.generator = message("generator");
  else if (generator.length > 64) errors.generator = message("longerThan", { max: 64 });
  put(errors, "width", decimalError(form.width, 1, 99999.9, 1));
  put(errors, "height", decimalError(form.height, 1, 99999.9, 1));
  put(errors, "basePrice", decimalError(form.basePrice, 0, 999999.99, 2));

  const schema: ParamField[] = [];
  const names = new Set<string>();
  for (const fieldForm of form.fields) {
    const before = original?.param_schema.find((field) => field.name === fieldForm.name.trim());
    const { field, error } = buildField(fieldForm, before);
    if (!field) errors[`field:${fieldForm.key}`] = error;
    else if (names.has(field.name)) errors[`field:${fieldForm.key}`] = message("duplicateField", { name: field.name });
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
      name_en: nameEn,
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
  const label = fieldLabel(field);
  const key = field.required === false ? "catalog.templates.fieldSummaryOptional" : "catalog.templates.fieldSummary";
  return i18n.global.t(key, { label, type: fieldTypeLabel(field.type) });
}
