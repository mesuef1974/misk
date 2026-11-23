import { appendPage, pageQuery } from "@/api/paging";
import {
  buildCalibrationDraft,
  buildMaterialDraft,
  buildTemplateDraft,
  emptyCalibrationForm,
  emptyMaterialForm,
  emptyTemplateForm,
  localToday,
  materialName,
  newSchemaField,
  parseChoices,
  templateFormFrom,
  templateName,
} from "@/domain/catalog";
import {
  buildRunDraft,
  emptyRunForm,
  formatDuration,
  groupPlacements,
  usedFraction,
} from "@/domain/production";
import { choiceLabel, fieldLabel, type ParamField } from "@/domain/params";
import { setLocale } from "@/i18n";
import type { ProductTemplate } from "@/services/catalog";
import type { Sheet } from "@/services/production";

describe("نموذج المادة", () => {
  it("ينظّف الاسم ويرسل الأعداد نصوصًا", () => {
    const { draft, errors } = buildMaterialDraft({
      ...emptyMaterialForm(),
      name: "  جلد   نباتي ",
      kind: "leather",
      thickness: 2,
      sheetCost: 45.5,
      supplier: " المورّد ",
    });
    expect(errors).toEqual({});
    expect(draft).toEqual({
      name: "جلد نباتي",
      name_en: "",
      kind: "leather",
      thickness_mm: "2",
      sheet_cost: "45.5",
      supplier: "المورّد",
      notes: "",
    });
  });

  it("يرفض الناقص والخارج عن حدود الحقول", () => {
    const { draft, errors } = buildMaterialDraft({ ...emptyMaterialForm(), thickness: 2.123, sheetCost: -1 });
    expect(draft).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["kind", "name", "sheetCost", "thickness"]);
  });
});

describe("نموذج المعايرة", () => {
  it("يبدأ بتاريخ اليوم المحلي", () => {
    expect(localToday(new Date(2026, 0, 5, 23, 30))).toBe("2026-01-05");
  });

  it("يبني المسودة ويترك خطوط/سم فارغة null", () => {
    const { draft } = buildCalibrationDraft({
      ...emptyCalibrationForm("2026-11-16"),
      operation: "engrave",
      power: 30,
      speed: 200,
      minLine: 0.4,
    });
    expect(draft).toEqual({
      operation: "engrave",
      power_pct: 30,
      speed_mm_s: "200",
      min_line_mm: "0.4",
      measured_on: "2026-11-16",
      passes: 1,
      lines_per_cm: null,
      notes: "",
    });
  });

  it("يرفض القدرة فوق 100 والحقول الفارغة", () => {
    const { draft, errors } = buildCalibrationDraft({ ...emptyCalibrationForm("2026-11-16"), power: 101 });
    expect(draft).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["minLine", "operation", "power", "speed"]);
  });
});

describe("نموذج القالب", () => {
  const base = { ...emptyTemplateForm(), slug: "name-tag", name: "ميدالية", generator: "name_tag", width: 80, height: 50 };

  it("يبني مخطط الحقول بأنواعها", () => {
    const { draft, errors } = buildTemplateDraft({
      ...base,
      fields: [
        { ...newSchemaField(1), name: "text", label: "الاسم", maxLength: 12 },
        { ...newSchemaField(2), name: "size", type: "int", min: 1, max: 5, required: false },
        { ...newSchemaField(3), name: "font", type: "choice", choices: "نسخ\nرقعة، نسخ" },
      ],
    });
    expect(errors).toEqual({});
    expect(draft?.param_schema).toEqual([
      { name: "text", type: "text", label: "الاسم", max_length: 12 },
      { name: "size", type: "int", required: false, min: 1, max: 5 },
      { name: "font", type: "choice", choices: ["نسخ", "رقعة"] },
    ]);
  });

  it("يعلّم الحقل المكرر والخيارات الفارغة والحدّين المعكوسين بمفتاح الحقل", () => {
    const { draft, errors } = buildTemplateDraft({
      ...base,
      fields: [
        { ...newSchemaField(1), name: "a" },
        { ...newSchemaField(2), name: "a" },
        { ...newSchemaField(3), name: "b", type: "choice" },
        { ...newSchemaField(4), name: "c", type: "int", min: 5, max: 1 },
      ],
    });
    expect(draft).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(["field:2", "field:3", "field:4"]);
  });

  it("يرفض المعرّف ذا المسافات", () => {
    expect(buildTemplateDraft({ ...base, slug: "name tag" }).errors.slug).toBeTruthy();
  });

  it("يبقي الخيارات الرقمية أرقامًا عند التعديل", () => {
    const original: ProductTemplate = {
      id: 1,
      slug: "ring",
      name: "خاتم",
      name_en: "",
      generator: "ring",
      width_mm: "30.0",
      height_mm: "30.0",
      safe_margin_mm: "3.0",
      base_price: "10.00",
      param_schema: [{ name: "size", type: "choice", choices: [16, 18] }],
    };
    const form = templateFormFrom(original);
    form.fields[0].choices += "\n20";
    expect(buildTemplateDraft(form, original).draft?.param_schema[0].choices).toEqual([16, 18, "20"]);
  });

  it("يفصل الخيارات بالسطر والفاصلة ويحذف المكرر", () => {
    expect(parseChoices(" أ ,ب،أ\n\nج ")).toEqual(["أ", "ب", "ج"]);
  });
});

describe("اسم القالب بلغة الصفحة", () => {
  it("الإنجليزي في الصفحة الإنجليزية إن أُدخل، وإلا العربي", async () => {
    const named = { name: "بطاقة مقوّسة", name_en: "Arched card" };
    const unnamed = { name: "خاتم", name_en: "" };
    expect(templateName(named)).toBe("بطاقة مقوّسة");
    await setLocale("en");
    expect(templateName(named)).toBe("Arched card");
    expect(templateName(unnamed)).toBe("خاتم");
  });
});

describe("اسم المادة وتسميات الحقول بلغة الصفحة", () => {
  const font: ParamField = {
    name: "الخط",
    type: "choice",
    label_en: "Font",
    choices: ["كايرو", "المراي"],
    choices_en: ["Cairo", "Almarai"],
  };

  it("العربية في الصفحة العربية، والإنجليزية في الإنجليزية إن أُدخلت", async () => {
    const wood = { name: "خشب زيزفون", name_en: "Basswood" };
    expect([materialName(wood), fieldLabel(font), choiceLabel(font, "كايرو")]).toEqual(["خشب زيزفون", "الخط", "كايرو"]);
    await setLocale("en");
    expect([materialName(wood), fieldLabel(font), choiceLabel(font, "المراي")]).toEqual(["Basswood", "Font", "Almarai"]);
    expect(materialName({ name: "جلد", name_en: "" })).toBe("جلد");
    expect(fieldLabel({ name: "النص", type: "text" })).toBe("النص");
    // قيمة حُفظت بخيار حُذف لاحقًا، وحقل بلا تسميات إنجليزية.
    expect(choiceLabel(font, "ثلث")).toBe("ثلث");
    expect(choiceLabel({ choices: ["أ"] }, "أ")).toBe("أ");
  });

  it("التسميات الإنجليزية تُحفظ مع القالب وتعود إلى نموذجه كما هي", () => {
    const original: ProductTemplate = {
      id: 2,
      slug: "lid",
      name: "غطاء",
      name_en: "Lid",
      generator: "jar_lid",
      width_mm: "70.0",
      height_mm: "70.0",
      safe_margin_mm: "3.0",
      base_price: "20.00",
      param_schema: [font],
    };
    const form = templateFormFrom(original);
    const { draft } = buildTemplateDraft(form, original);
    expect(draft?.name_en).toBe("Lid");
    expect(draft?.param_schema).toEqual([font]);

    form.fields[0].choicesEn = "Cairo";
    expect(buildTemplateDraft(form, original).errors["field:1"]).toBeTruthy();
    form.fields[0].choicesEn = "";
    expect(buildTemplateDraft(form, original).draft?.param_schema[0].choices_en).toBeUndefined();
  });
});

describe("حسابات اللوح", () => {
  const sara = { order_item_id: 10, order_id: 3, customer_name: "أم سارة", template_slug: "card", name: "بطاقة", variant_code: "", cut_file_url: "", personalization: [] };
  const noor = { order_item_id: 11, order_id: 4, customer_name: "نور", template_slug: "design-4", name: "علبة هدية", variant_code: "02", cut_file_url: "/media/designs/files/a.svg", personalization: [] };
  const sheet: Sheet = {
    id: 1,
    material_id: 7,
    width_mm: "600.0",
    height_mm: "300.0",
    status: "planned",
    placements: [
      { ...sara, copy_index: 0, x_mm: "5.0", y_mm: "5.0", width_mm: "300.0", height_mm: "150.0" },
      { ...noor, copy_index: 0, x_mm: "308.0", y_mm: "5.0", width_mm: "100.0", height_mm: "90.0" },
      { ...sara, copy_index: 1, x_mm: "5.0", y_mm: "158.0", width_mm: "300.0", height_mm: "150.0" },
    ],
    runs: [],
  };

  it("تحسب نسبة الاستعمال وتجمّع القطع ببندها", () => {
    expect(usedFraction(sheet)).toBeCloseTo(0.55);
    expect(usedFraction({ ...sheet, width_mm: "0" })).toBe(0);
    expect(groupPlacements(sheet)).toEqual([
      { number: 1, orderItemId: 10, orderId: 3, customerName: "أم سارة", templateSlug: "card", name: "بطاقة", variantCode: "", cutFiles: [], personalization: [], copies: 2 },
      { number: 2, orderItemId: 11, orderId: 4, customerName: "نور", templateSlug: "design-4", name: "علبة هدية", variantCode: "02", cutFiles: ["/media/designs/files/a.svg"], personalization: [], copies: 1 },
    ]);
  });

  it("تبني استعلام الصفحة وتضيف الصفحة التالية بلا تكرار", () => {
    expect([pageQuery(), pageQuery({ status: "", offset: 0 })]).toEqual(["", ""]);
    expect(pageQuery({ status: "ready", offset: 50 })).toBe("?status=ready&offset=50");
    expect(appendPage([{ id: 3 }, { id: 2 }], [{ id: 2 }, { id: 1 }])).toEqual([{ id: 3 }, { id: 2 }, { id: 1 }]);
  });

  it("تنسّق المدة", () => {
    expect([formatDuration(45), formatDuration(120), formatDuration(125)]).toEqual(["45 ث", "2 د", "2 د 5 ث"]);
  });
});

describe("نموذج التشغيل", () => {
  it("يجمع الدقائق والثواني", () => {
    expect(buildRunDraft({ ...emptyRunForm(), minutes: 3, seconds: 20, calibrationId: 4 }).draft).toEqual({
      duration_s: 200,
      outcome: "ok",
      calibration_id: 4,
      notes: "",
    });
  });

  it("يرفض المدة الفارغة والثواني فوق 59", () => {
    expect(buildRunDraft(emptyRunForm()).errors.duration).toBeTruthy();
    expect(buildRunDraft({ ...emptyRunForm(), minutes: 1, seconds: 60 }).errors.duration).toBeTruthy();
  });
});
