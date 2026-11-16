import { buildDraft, estimateTotal, newItem, withTemplate, type OrderForm } from "./orderForm";
import { formatDate, formatMoney, nextStatuses, statusLabel } from "./orders";
import { cleanParams, emptyParams, type ParamField } from "./params";

const schema: ParamField[] = [
  { name: "name", type: "text", max_length: 5 },
  { name: "size", type: "int", min: 1, max: 9 },
  { name: "gift", type: "bool" },
  { name: "font", type: "choice", choices: ["ثلث", "رقعة"] },
  { name: "note", type: "text", required: false },
];
const templates = [{ slug: "card", param_schema: schema, base_price: "25.00" }];

describe("معاملات القالب", () => {
  it("يبدأ النموذج فارغًا والمنطقي false", () => {
    expect(emptyParams(schema)).toEqual({ name: "", size: "", gift: false, font: "", note: "" });
  });

  it("ينظّف النص ويحذف الاختياري الفارغ", () => {
    const result = cleanParams(schema, { name: " أ  ب ", size: 3, gift: false, font: "ثلث", note: "" });
    expect(result.errors).toEqual({});
    expect(result.params).toEqual({ name: "أ ب", size: 3, gift: false, font: "ثلث" });
  });

  it("يبلّغ عن المطلوب والمدى والطول والخيار", () => {
    const result = cleanParams(schema, { name: "طويل جدًّا", size: 10, gift: false, font: "كوفي", note: "" });
    expect(result.errors).toEqual({
      name: "أطول من 5 حرفًا",
      size: "خارج المدى المسموح",
      font: "ليست من الخيارات",
    });
    expect(cleanParams(schema, emptyParams(schema)).errors).toMatchObject({ name: "مطلوب", size: "مطلوب" });
    expect(cleanParams(schema, { ...emptyParams(schema), size: 1.5 }).errors.size).toBe("عدد صحيح");
  });
});

describe("حالات الطلب", () => {
  it("يعرض الانتقالات المسموحة فقط", () => {
    expect(nextStatuses("draft")).toEqual(["confirmed", "cancelled"]);
    expect(nextStatuses("ready")).toEqual(["delivered"]);
    expect(nextStatuses("delivered")).toEqual([]);
    expect(nextStatuses("مجهولة")).toEqual([]);
  });

  it("يسمّي الحالة ويترك المجهولة كما هي", () => {
    expect(statusLabel("in_production")).toBe("قيد التنفيذ");
    expect(statusLabel("x")).toBe("x");
  });

  it("ينسّق المال والتاريخ", () => {
    expect(formatMoney("1250.5")).toBe("1,250.50 ر.ق");
    expect(formatMoney("ليس رقمًا")).toBe("0.00 ر.ق");
    expect(formatDate("2026-12-01")).toContain("2026");
    expect(formatDate(null)).toBe("");
  });
});

describe("نموذج الطلب الجديد", () => {
  function form(overrides: Partial<OrderForm> = {}): OrderForm {
    const item = {
      ...withTemplate(newItem(1), templates[0]),
      materialId: 7 as const,
      params: { name: "سارة", size: 2, gift: true, font: "رقعة", note: "" },
    };
    return { customerName: "  أم  سارة ", occasionDate: "", notes: " ", items: [item], ...overrides };
  }

  it("يبني ما يرسله الخادم ويترك السعر الفارغ null", () => {
    const { draft, errors } = buildDraft(form(), "ref-1", templates);
    expect(errors).toEqual({ items: {} });
    expect(draft).toEqual({
      client_ref: "ref-1",
      customer_name: "أم سارة",
      occasion_date: null,
      notes: "",
      items: [
        {
          template_slug: "card",
          material_id: 7,
          params: { name: "سارة", size: 2, gift: true, font: "رقعة" },
          quantity: 1,
          unit_price: null,
        },
      ],
    });
  });

  it("يرسل السعر المكتوب نصًّا والتاريخ كما هو", () => {
    const base = form({ occasionDate: "2026-12-01" });
    base.items[0].unitPrice = 30.5;
    const { draft } = buildDraft(base, "ref-1", templates);
    expect(draft?.occasion_date).toBe("2026-12-01");
    expect(draft?.items[0].unit_price).toBe("30.5");
  });

  it("يرفض النموذج الناقص ويربط الخطأ ببنده وحقله", () => {
    const { draft, errors } = buildDraft(
      { customerName: " ", occasionDate: "", notes: "", items: [{ ...newItem(4), quantity: 0, unitPrice: -1 }] },
      "ref-1",
      templates,
    );
    expect(draft).toBeNull();
    expect(errors.customerName).toBe("اسم الزبون مطلوب");
    expect(errors.items[4]).toEqual({
      template: "اختر القالب",
      material: "اختر المادة",
      quantity: "عدد صحيح، 1 أو أكثر",
      unitPrice: "السعر لا يكون سالبًا",
    });
  });

  it("يعلّم معاملات القالب الناقصة", () => {
    const base = form();
    base.items[0].params = emptyParams(schema);
    expect(buildDraft(base, "ref-1", templates).errors.items[1]).toMatchObject({ "param:name": "مطلوب" });
  });

  it("تغيير القالب يصفّر المعاملات", () => {
    const changed = withTemplate({ ...newItem(1), params: { old: "x" } }, templates[0]);
    expect(changed.templateSlug).toBe("card");
    expect(changed.params).toEqual(emptyParams(schema));
  });

  it("يقدّر المجموع بسعر القالب حين يُترك السعر فارغًا", () => {
    const items = [
      { ...newItem(1), templateSlug: "card", quantity: 2 as const },
      { ...newItem(2), templateSlug: "card", quantity: 1 as const, unitPrice: 10 as const },
      { ...newItem(3), quantity: "" as const },
    ];
    expect(estimateTotal(items, templates)).toBe(60);
  });
});
