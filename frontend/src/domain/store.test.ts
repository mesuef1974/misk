import { ApiError } from "@/api/client";
import type { ParamField } from "@/domain/params";
import { setLocale } from "@/i18n";
import type { FieldLimit } from "@/services/store";
import { formatDay, initialParams, limitFor, lineName, localized, safePaymentUrl, storeError, svgDataUrl, textLength } from "./store";

describe("أخطاء مسارات المتجر", () => {
  it("يقرأ الرمز وأخطاء الحقول والاقتراحات وأقرب جاهزية", () => {
    const error = new ApiError(422, "لا نلحق تاريخ المناسبة", {
      code: "occasion_too_soon",
      detail: "لا نلحق تاريخ المناسبة",
      fields: { occasion_date: { code: "date_in_past", message: "التاريخ مضى" } },
      suggestions: ["wall-plaque", 5],
      ready_on: "2026-12-01",
    });
    expect(storeError(error, "x")).toEqual({
      code: "occasion_too_soon",
      message: "لا نلحق تاريخ المناسبة",
      fields: { occasion_date: "التاريخ مضى" },
      suggestions: ["wall-plaque"],
      readyOn: "2026-12-01",
    });
  });

  it("لا يثق بشكل الجسم: رد بلا JSON أو بحقول مشوّهة يعود بلا رمز ولا حقول", () => {
    expect(storeError(new ApiError(502, "تعذّر إتمام العملية (502)"), "x")).toEqual({
      code: "",
      message: "تعذّر إتمام العملية (502)",
      fields: {},
      suggestions: [],
      readyOn: null,
    });
    const odd = storeError(new ApiError(422, "رسالة", { code: 7, fields: { a: null, b: "نص", c: { message: 3 } }, suggestions: "x" }), "x");
    expect(odd).toMatchObject({ code: "", fields: {}, suggestions: [] });
    expect(storeError(new Error("boom"), "خطأ غير متوقع").message).toBe("خطأ غير متوقع");
  });
});

describe("المصمِّم", () => {
  const schema: ParamField[] = [
    { name: "الاسم", type: "text", max_length: 20 },
    { name: "الخط", type: "choice", choices: ["كايرو", "المراي"] },
    { name: "النمط", type: "choice", choices: ["أ", "ب"], required: false },
    { name: "ثقب", type: "bool" },
    { name: "العدد", type: "int", min: 1 },
  ];

  it("قيم البدء: أول خيار للاختيار المطلوب، وفارغ لغيره", () => {
    expect(initialParams(schema)).toEqual({ الاسم: "", الخط: "كايرو", النمط: "", ثقب: false, العدد: "" });
  });

  it("حدّ الحقل هو الصف المطابق لقيم الاختيار الجارية", () => {
    const limits: FieldLimit[] = [
      { field: "الاسم", when: { الخط: "كايرو" }, max_chars: 12, min_text_height_mm: 3 },
      { field: "الاسم", when: { الخط: "المراي" }, max_chars: 9, min_text_height_mm: 3.4 },
    ];
    expect(limitFor(limits, "الاسم", { الخط: "المراي" })?.max_chars).toBe(9);
    expect(limitFor(limits, "الاسم", { الخط: "غيره" })).toBeUndefined();
    expect(limitFor(limits, "سطر", { الخط: "كايرو" })).toBeUndefined();
  });

  it("يعدّ الحروف بعد طيّ الفراغات كما يعدّها الخادم", () => {
    expect(textLength("  محمد   علي ")).toBe(8);
    expect(textLength(5)).toBe(0);
    expect(textLength(undefined)).toBe(0);
  });

  it("ملف القص يُعرض صورةً بعنوان بيانات مرمَّز", () => {
    const url = svgDataUrl('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><text>م#</text></svg>');
    expect(url.startsWith("data:image/svg+xml;charset=utf-8,")).toBe(true);
    expect(url).not.toContain("<");
    expect(url).not.toContain("#");
  });
});

describe("عرض المتجر", () => {
  it("الاسم بلغة الصفحة، والعربي حين لا إنجليزي", async () => {
    expect(localized("لوحة", "Plaque")).toBe("لوحة");
    await setLocale("en");
    expect(localized("لوحة", "Plaque")).toBe("Plaque");
    expect(localized("لوحة", "")).toBe("لوحة");
  });

  it("بند التصميم الجاهز يُسمّى برمز نسخته، وبند المصمِّم باسمه وحده", async () => {
    const box = { name: "علبة هدية", name_en: "Gift box" };
    expect(lineName({ ...box, variant_code: "02" })).toBe("علبة هدية (نسخة 02)");
    expect(lineName({ ...box, variant_code: "" })).toBe("علبة هدية");
    await setLocale("en");
    expect(lineName({ ...box, variant_code: "02" })).toBe("Gift box (version 02)");
  });

  it("اليوم باسمه وبأرقام لاتينية في اللغتين", async () => {
    expect(formatDay("2026-11-28")).toBe("السبت، 28 نوفمبر");
    await setLocale("en");
    expect(formatDay("2026-11-28")).toBe("Saturday 28 November");
  });

  it("رابط الدفع: مسار داخلي أو https وحدهما", () => {
    expect(safePaymentUrl("/checkout/test-pay/test_ab")).toBe("/checkout/test-pay/test_ab");
    expect(safePaymentUrl("https://pay.example/s/1")).toBe("https://pay.example/s/1");
    for (const bad of ["javascript:alert(1)", "//evil.example", "/\\evil.example", "http://pay.example", "", null, undefined]) {
      expect(safePaymentUrl(bad)).toBe("");
    }
  });
});
