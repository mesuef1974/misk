import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { ApiError } from "@/api/client";
import { routes } from "@/router";
import { catalogService, type Calibration, type Material, type ProductTemplate } from "@/services/catalog";
import { ordersService, type Order } from "@/services/orders";
import { productionService, type PlanJob, type Run, type Sheet } from "@/services/production";
import { PlanCancelled, PLAN_POLL_MS, PLAN_TIMEOUT_MESSAGE, useProductionStore } from "@/stores/production";
import { useCatalogStore } from "@/stores/catalog";
import { sessionService } from "@/services/session";
import HomePage from "./HomePage.vue";
import MaterialsPage from "./MaterialsPage.vue";
import ProductionPage from "./ProductionPage.vue";
import TemplatesPage from "./TemplatesPage.vue";

vi.mock("@/services/catalog", () => ({
  catalogService: {
    materials: vi.fn(),
    templates: vi.fn(),
    saveMaterial: vi.fn(),
    saveTemplate: vi.fn(),
    calibrations: vi.fn(),
    addCalibration: vi.fn(),
  },
}));
vi.mock("@/services/orders", () => ({
  ordersService: { list: vi.fn(), get: vi.fn(), create: vi.fn(), transition: vi.fn() },
}));
vi.mock("@/services/production", () => ({
  productionService: { sheets: vi.fn(), plan: vi.fn(), planJob: vi.fn(), recordRun: vi.fn(), scrap: vi.fn() },
}));
vi.mock("@/services/session", () => ({
  sessionService: { me: vi.fn(), login: vi.fn(), logout: vi.fn() },
}));

function job(overrides: Partial<PlanJob> = {}): PlanJob {
  return { id: "", status: "done", sheets: [], error: "", ...overrides };
}

const leather: Material = {
  id: 7,
  name: "جلد نباتي",
  kind: "leather",
  thickness_mm: "2.00",
  sheet_width_mm: "600.0",
  sheet_height_mm: "305.0",
  sheet_cost: "45.00",
  supplier: "مدبغة",
  notes: "",
};
const card: ProductTemplate = {
  id: 1,
  slug: "card",
  name: "بطاقة مقوّسة",
  generator: "card",
  width_mm: "90.0",
  height_mm: "55.0",
  safe_margin_mm: "3.0",
  base_price: "25.00",
  param_schema: [{ name: "name", type: "text", label: "الاسم" }],
};
const calibration: Calibration = {
  id: 3,
  material_id: 7,
  operation: "engrave",
  power_pct: 30,
  speed_mm_s: "200.0",
  passes: 1,
  lines_per_cm: null,
  min_line_mm: "0.40",
  measured_on: "2026-11-16",
  notes: "",
};
const order: Order = {
  id: 4,
  client_ref: "r",
  customer_name: "أم سارة",
  status: "confirmed",
  occasion_date: null,
  notes: "",
  total: "50.00",
  items: [{ id: 10, template_slug: "card", material_id: 7, params: { name: "سارة" }, quantity: 2, unit_price: "25.00" }],
};

const piece = { order_item_id: 10, order_id: 4, customer_name: "أم سارة", template_slug: "card" };

function sheet(overrides: Partial<Sheet> = {}): Sheet {
  return {
    id: 1,
    material_id: 7,
    width_mm: "600.0",
    height_mm: "305.0",
    status: "planned",
    placements: [
      { ...piece, copy_index: 0, x_mm: "5.0", y_mm: "5.0", width_mm: "90.0", height_mm: "55.0" },
      { ...piece, copy_index: 1, x_mm: "98.0", y_mm: "5.0", width_mm: "90.0", height_mm: "55.0" },
    ],
    runs: [],
    ...overrides,
  };
}

function sheetsPage(items: Sheet[] = [sheet()], count = items.length) {
  const counts: Record<string, number> = {};
  for (const item of items) counts[item.status] = (counts[item.status] ?? 0) + 1;
  return { items, count, counts };
}

const okRun: Run = {
  id: 5,
  sheet_id: 1,
  outcome: "ok",
  duration_s: 200,
  material_cost: "45.00",
  notes: "",
  created_at: "2026-11-16T10:00:00+00:00",
};

let router: Router;

async function show(component: object, path: string) {
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

function button(page: ReturnType<typeof mount>, text: string) {
  const found = page.findAll("button").find((candidate) => candidate.text() === text);
  if (!found) throw new Error(`لا زر بنص «${text}»`);
  return found;
}

beforeEach(() => {
  setActivePinia(createPinia());
  router = createRouter({ history: createMemoryHistory(), routes });
  vi.mocked(catalogService.materials).mockReset().mockResolvedValue([leather]);
  vi.mocked(catalogService.templates).mockReset().mockResolvedValue([card]);
  vi.mocked(catalogService.calibrations).mockReset().mockResolvedValue([calibration]);
  vi.mocked(catalogService.saveMaterial).mockReset();
  vi.mocked(catalogService.saveTemplate).mockReset();
  vi.mocked(catalogService.addCalibration).mockReset();
  vi.mocked(ordersService.list).mockReset().mockResolvedValue({ items: [order], count: 1, counts: { confirmed: 1 } });
  vi.mocked(productionService.sheets).mockReset().mockResolvedValue(sheetsPage());
  vi.mocked(productionService.plan).mockReset();
  vi.mocked(productionService.planJob).mockReset();
  vi.mocked(productionService.recordRun).mockReset();
  vi.mocked(productionService.scrap).mockReset();
  vi.mocked(sessionService.me).mockReset().mockResolvedValue({ id: 1, username: "staff", is_staff: true, admin_url: "/admin/" });
});

describe("صفحة المواد", () => {
  it("تعرض المواد وتضيف مادة جديدة", async () => {
    const wood: Material = { ...leather, id: 8, name: "خشب بتولا", kind: "wood", thickness_mm: "3.00" };
    vi.mocked(catalogService.saveMaterial).mockResolvedValue(wood);
    const page = await show(MaterialsPage, "/materials");
    expect(page.text()).toContain("جلد نباتي");
    expect(page.text()).toContain("600.0 × 305.0 مم");

    await button(page, "مادة جديدة").trigger("click");
    await page.get("form").trigger("submit");
    expect(page.findAll(".error").length).toBeGreaterThan(0);
    expect(catalogService.saveMaterial).not.toHaveBeenCalled();

    const inputs = page.findAll(".editor input");
    await inputs[0].setValue("خشب بتولا");
    await inputs[1].setValue("3");
    await page.get(".editor select").setValue("wood");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(catalogService.saveMaterial).toHaveBeenCalledWith({
      name: "خشب بتولا",
      kind: "wood",
      thickness_mm: "3",
      sheet_cost: "0",
      supplier: "",
      notes: "",
    });
    expect(page.find(".editor").exists()).toBe(false);
    expect(page.findAll(".material")).toHaveLength(2);
  });

  it("تقفل مفتاح المادة عند التعديل وتعرض خطأ الخادم", async () => {
    vi.mocked(catalogService.saveMaterial).mockRejectedValue(new ApiError(422, "قيمة غير صالحة"));
    const page = await show(MaterialsPage, "/materials");
    await button(page, "تعديل").trigger("click");
    const inputs = page.findAll(".editor input");
    expect(inputs[0].attributes("disabled")).toBeDefined();
    expect(inputs[1].attributes("disabled")).toBeDefined();
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toContain("قيمة غير صالحة");
    expect(page.find(".editor").exists()).toBe(true);
  });

  it("تفتح معايرات المادة وتسجّل معايرة", async () => {
    vi.mocked(catalogService.addCalibration).mockResolvedValue({ ...calibration, id: 9, operation: "cut", power_pct: 80 });
    const page = await show(MaterialsPage, "/materials");
    await button(page, "المعايرات").trigger("click");
    await flushPromises();
    expect(catalogService.calibrations).toHaveBeenCalledWith(7);
    expect(page.findAll("tbody tr")).toHaveLength(1);

    const form = page.get(".calibrations form");
    await form.get("select").setValue("cut");
    const inputs = form.findAll("input");
    await inputs[0].setValue("80");
    await inputs[1].setValue("12.5");
    await inputs[4].setValue("0.3");
    await form.trigger("submit");
    await flushPromises();
    expect(vi.mocked(catalogService.addCalibration).mock.calls[0][1]).toMatchObject({
      operation: "cut",
      power_pct: 80,
      speed_mm_s: "12.5",
      min_line_mm: "0.3",
      passes: 1,
      lines_per_cm: null,
    });
    expect(page.findAll("tbody tr")).toHaveLength(2);
  });
});

describe("صفحة القوالب", () => {
  it("تعدّل قالبًا وتضيف حقلًا إلى مخططه", async () => {
    vi.mocked(catalogService.saveTemplate).mockImplementation(async (draft) => ({ ...card, ...draft }));
    const page = await show(TemplatesPage, "/templates");
    expect(page.text()).toContain("الاسم (نص)");

    await button(page, "تعديل").trigger("click");
    expect(page.get(".editor input").attributes("disabled")).toBeDefined();
    await button(page, "إضافة حقل").trigger("click");
    const added = page.findAll(".schema-field")[1];
    await added.get("input").setValue("gift");
    await added.get("select").setValue("bool");
    await page.get("form").trigger("submit");
    await flushPromises();

    expect(vi.mocked(catalogService.saveTemplate).mock.calls[0][0]).toMatchObject({
      slug: "card",
      width_mm: "90",
      param_schema: [
        { name: "name", type: "text", label: "الاسم" },
        { name: "gift", type: "bool" },
      ],
    });
    expect(page.find(".editor").exists()).toBe(false);
    expect(page.text()).toContain("gift (نعم/لا)");
  });

  it("تمنع الحفظ بحقل بلا اسم", async () => {
    const page = await show(TemplatesPage, "/templates");
    await button(page, "تعديل").trigger("click");
    await button(page, "إضافة حقل").trigger("click");
    await page.get("form").trigger("submit");
    expect(page.text()).toContain("اسم الحقل مطلوب");
    expect(catalogService.saveTemplate).not.toHaveBeenCalled();
  });
});

describe("صفحة الإنتاج", () => {
  it("ترسم اللوح وتسمّي قطعه بطلبها", async () => {
    const page = await show(ProductionPage, "/production");
    expect(page.findAll("svg .piece")).toHaveLength(2);
    expect(page.get(".legend").text()).toContain("بطاقة مقوّسة — أم سارة");
    expect(page.get(".legend").text()).toContain("× 2");
    expect(page.get(".legend a").text()).toBe("طلب 4");
    expect(page.get(".head").text()).toContain("جلد نباتي");
    expect(ordersService.list).not.toHaveBeenCalled(); // أسماء القطع من اللوح نفسه، لا من قائمة الطلبات
  });

  it("تصفّي من الخادم وتعرض سجل تشغيل اللوح وتحمّل المزيد", async () => {
    const done = sheet({ id: 3, status: "done", runs: [{ ...okRun, sheet_id: 3, notes: "حافة محترقة قليلًا" }] });
    vi.mocked(productionService.sheets)
      .mockResolvedValueOnce({ items: [sheet()], count: 1, counts: { planned: 1, done: 2 } })
      .mockResolvedValueOnce({ items: [done], count: 2, counts: { planned: 1, done: 2 } })
      .mockResolvedValueOnce({ items: [sheet({ id: 2, status: "done" })], count: 2, counts: { planned: 1, done: 2 } });
    const page = await show(ProductionPage, "/production");
    expect(page.findAll(".chip")[0].text()).toContain("3");
    expect(page.find(".runs").exists()).toBe(false);

    await page.findAll(".chip").find((chip) => chip.text().startsWith("نُفِّذ"))!.trigger("click");
    await flushPromises();
    expect(productionService.sheets).toHaveBeenLastCalledWith({ status: "done" });
    expect(page.get(".runs").text()).toContain("نجح · 3 د 20 ث · كلفة المادة 45.00 ر.ق");
    expect(page.get(".runs").text()).toContain("حافة محترقة قليلًا");

    await page.get(".more button").trigger("click");
    await flushPromises();
    expect(productionService.sheets).toHaveBeenLastCalledWith({ status: "done", offset: 1 });
    expect(page.findAll(".sheet-card")).toHaveLength(2);
    expect(page.find(".more").exists()).toBe(false);
  });

  it("تتلف اللوح بعد تأكيد وتعرض رفض الخادم", async () => {
    vi.mocked(productionService.scrap)
      .mockRejectedValueOnce(new ApiError(409, "اللوح 1 ليس مخطَّطًا (نُفِّذ)"))
      .mockResolvedValueOnce(sheet({ status: "scrapped", placements: [] }));
    const page = await show(ProductionPage, "/production");
    await button(page, "إتلاف اللوح").trigger("click");
    expect(productionService.scrap).not.toHaveBeenCalled();
    await button(page, "تراجع").trigger("click");
    expect(page.findAll("button").some((candidate) => candidate.text() === "تأكيد الإتلاف")).toBe(false);

    await button(page, "إتلاف اللوح").trigger("click");
    await button(page, "تأكيد الإتلاف").trigger("click");
    await flushPromises();
    expect(page.get('.sheet-card [role="alert"]').text()).toContain("ليس مخطَّطًا");

    await button(page, "إتلاف اللوح").trigger("click");
    await button(page, "تأكيد الإتلاف").trigger("click");
    await flushPromises();
    expect(productionService.scrap).toHaveBeenLastCalledWith(1);
    expect(page.get(".state").text()).toBe("تالف");
    expect(page.findAll("svg .piece")).toHaveLength(0);
    expect(page.findAll("button").some((candidate) => candidate.text() === "إتلاف اللوح")).toBe(false);
    expect(page.findAll(".chip").find((chip) => chip.text().startsWith("تالف"))!.text()).toContain("1");
  });

  it("تخطّط ألواح المادة وتذكر حين لا قطع تنتظر", async () => {
    vi.mocked(productionService.plan)
      .mockResolvedValueOnce(job({ sheets: [sheet({ id: 2 })] }))
      .mockResolvedValueOnce(job());
    const page = await show(ProductionPage, "/production");
    await page.get(".plan select").setValue("7");
    await page.get(".plan").trigger("submit");
    await flushPromises();
    expect(productionService.plan).toHaveBeenCalledWith(7);
    expect(page.findAll(".sheet-card")).toHaveLength(2);
    expect(page.get(".plan .notice").text()).toContain("خُطِّطت 2 قطعة على 1 لوح");

    await page.get(".plan").trigger("submit");
    await flushPromises();
    expect(page.get(".plan .notice").text()).toContain("لا قطع تنتظر التخطيط");
  });

  it("تستطلع التخطيط في الخلفية حتى ينتهي", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    try {
      vi.mocked(productionService.plan).mockResolvedValueOnce(job({ id: "j1", status: "pending" }));
      vi.mocked(productionService.planJob)
        .mockResolvedValueOnce(job({ id: "j1", status: "pending" }))
        .mockResolvedValueOnce(job({ id: "j1", sheets: [sheet({ id: 2 })] }));
      const page = await show(ProductionPage, "/production");
      await page.get(".plan select").setValue("7");
      await page.get(".plan").trigger("submit");
      await vi.runAllTimersAsync();
      await flushPromises();
      expect(productionService.planJob).toHaveBeenCalledTimes(2);
      expect(productionService.planJob).toHaveBeenLastCalledWith("j1");
      expect(page.findAll(".sheet-card")).toHaveLength(2);
      expect(page.get(".plan .notice").text()).toContain("خُطِّطت 2 قطعة على 1 لوح");
    } finally {
      vi.useRealTimers();
    }
  });

  it("تعرض فشل التخطيط في الخلفية وتتوقف عن الاستطلاع بعد حدّه", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    try {
      vi.mocked(productionService.plan)
        .mockResolvedValueOnce(job({ id: "j1", status: "pending" }))
        .mockResolvedValueOnce(job({ id: "j2", status: "pending" }));
      vi.mocked(productionService.planJob)
        .mockResolvedValueOnce(job({ id: "j1", status: "failed", error: "القطعة أكبر من اللوح بعد الهامش" }))
        .mockResolvedValue(job({ id: "j2", status: "pending" }));
      const page = await show(ProductionPage, "/production");
      await page.get(".plan select").setValue("7");
      await page.get(".plan").trigger("submit");
      await vi.runAllTimersAsync();
      await flushPromises();
      expect(page.get('.plan [role="alert"]').text()).toContain("أكبر من اللوح");

      await page.get(".plan").trigger("submit");
      await vi.runAllTimersAsync();
      await flushPromises();
      expect(productionService.planJob).toHaveBeenCalledTimes(1 + PLAN_POLL_MS.length);
      expect(page.get('.plan [role="alert"]').text()).toContain(PLAN_TIMEOUT_MESSAGE);
    } finally {
      vi.useRealTimers();
    }
  });

  it("تعرض رفض التخطيط من الخادم", async () => {
    vi.mocked(productionService.plan).mockRejectedValue(new ApiError(422, "القطعة أكبر من اللوح بعد الهامش"));
    const page = await show(ProductionPage, "/production");
    await page.get(".plan select").setValue("7");
    await page.get(".plan").trigger("submit");
    await flushPromises();
    expect(page.get('.plan [role="alert"]').text()).toContain("أكبر من اللوح");
  });

  it("تسجّل التشغيل بمفتاح واحد يبقى عند إعادة المحاولة ثم تغلق اللوح", async () => {
    vi.mocked(productionService.recordRun)
      .mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"))
      .mockResolvedValueOnce(okRun);
    const page = await show(ProductionPage, "/production");
    await button(page, "تسجيل تشغيل").trigger("click");
    await flushPromises();
    const form = page.get(".run");
    await form.trigger("submit");
    expect(form.text()).toContain("مدة التشغيل مطلوبة");

    const inputs = form.findAll("input");
    await inputs[0].setValue("3");
    await inputs[1].setValue("20");
    await form.findAll("select")[1].setValue("3");
    await form.trigger("submit");
    await flushPromises();
    expect(form.get('[role="alert"]').text()).toContain("تعذّر الاتصال");

    await form.trigger("submit");
    await flushPromises();
    const calls = vi.mocked(productionService.recordRun).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][1]).toEqual({ duration_s: 200, outcome: "ok", calibration_id: 3, notes: "" });
    expect(calls[0][2]).toMatch(/^[0-9a-f-]{36}$/);
    expect(calls[1][2]).toBe(calls[0][2]);

    expect(page.find(".run").exists()).toBe(false);
    expect(page.get(".state").text()).toBe("نُفِّذ");
    expect(page.get(".runs").text()).toContain("نجح · 3 د 20 ث · كلفة المادة 45.00 ر.ق");
    expect(page.findAll("button").some((candidate) => candidate.text() === "تسجيل تشغيل")).toBe(false);
  });
});

describe("اللوحة الرئيسية", () => {
  it("تعرض للمشرف أعداد الطلبات المفتوحة والألواح والكتالوج", async () => {
    const page = await show(HomePage, "/");
    const tiles = page.findAll(".tile").map((tile) => tile.text());
    expect(tiles).toContain("1مؤكَّد");
    expect(tiles).toContain("0مسودة");
    expect(tiles).toContain("1ألواح تنتظر التشغيل");
    expect(tiles).toContain("1مواد");
  });

  it("تعرض الاسم شعارًا بلون السمة لا نصًّا", async () => {
    const page = await show(HomePage, "/");
    const heading = page.get("h1");
    expect(heading.text()).toBe("");
    expect(heading.attributes("aria-label")).toBeDefined();
    // العودي السمة الافتراضية: ملف PNG لها، ولكل سمة ملفها.
    expect(heading.get("img").attributes("src")).toContain("misk-oud.png");
  });

  it("تحمّل البيانات مرة واحدة عند أول فتح", async () => {
    await show(HomePage, "/");
    expect(ordersService.list).toHaveBeenCalledTimes(1);
    expect(productionService.sheets).toHaveBeenCalledTimes(1);
    expect(catalogService.materials).toHaveBeenCalledTimes(1);
  });

  it("تدعو غير المشرف إلى الدخول ولا تطلب بيانات", async () => {
    vi.mocked(sessionService.me).mockResolvedValue(null);
    const page = await show(HomePage, "/");
    expect(page.text()).toContain("دخول المشرف");
    expect(page.find(".tile").exists()).toBe(false);
    expect(ordersService.list).not.toHaveBeenCalled();
  });
});

describe("مخزن الإنتاج", () => {
  it("يتجاهل «تحميل المزيد» أثناء تحميل تصفية جديدة", async () => {
    vi.mocked(productionService.sheets).mockResolvedValueOnce(sheetsPage([sheet()], 3));
    const store = useProductionStore();
    await store.load();
    let finish: (page: ReturnType<typeof sheetsPage>) => void = () => {};
    vi.mocked(productionService.sheets).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    const filtering = store.load("done");
    await store.loadMore();
    expect(productionService.sheets).toHaveBeenCalledTimes(2);
    finish(sheetsPage([sheet({ id: 3, status: "done" })]));
    await filtering;
    expect(store.sheets.map((candidate) => candidate.id)).toEqual([3]);
  });

  it("يواصل استطلاع التخطيط بعد خطأ عابر", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    try {
      vi.mocked(productionService.plan).mockResolvedValueOnce(job({ id: "j1", status: "pending" }));
      vi.mocked(productionService.planJob)
        .mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"))
        .mockRejectedValueOnce(new ApiError(503, "الخدمة غير متاحة"))
        .mockResolvedValueOnce(job({ id: "j1", sheets: [sheet({ id: 2 })] }));
      const store = useProductionStore();
      const planning = store.plan(7);
      await vi.runAllTimersAsync();
      expect((await planning).map((candidate) => candidate.id)).toEqual([2]);
      expect(productionService.planJob).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("يوقف الاستطلاع عند خطأ غير عابر", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    try {
      vi.mocked(productionService.plan).mockResolvedValueOnce(job({ id: "j1", status: "pending" }));
      vi.mocked(productionService.planJob).mockRejectedValueOnce(new ApiError(403, "للمشرفين فقط"));
      const store = useProductionStore();
      const planning = store.plan(7).catch((error: unknown) => error);
      await vi.runAllTimersAsync();
      expect(await planning).toMatchObject({ status: 403 });
      expect(productionService.planJob).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("التخطيط والتصفية بعد الإيقاف والمسح", () => {
  it("يتوقف الاستطلاع عند مغادرة الصفحة", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    try {
      vi.mocked(productionService.plan).mockResolvedValueOnce(job({ id: "j1", status: "pending" }));
      vi.mocked(productionService.planJob).mockResolvedValue(job({ id: "j1", status: "pending" }));
      const store = useProductionStore();
      const planning = store.plan(7).catch((error: unknown) => error);
      await flushPromises();
      store.stopPlanning();
      await vi.runAllTimersAsync();
      expect(await planning).toBeInstanceOf(PlanCancelled);
      expect(productionService.planJob).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("لا يكتب تخطيط بدأ قبل المسح في المخزن", async () => {
    let finish: (value: PlanJob) => void = () => {};
    vi.mocked(productionService.plan).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    const store = useProductionStore();
    const planning = store.plan(7).catch((error: unknown) => error);
    store.clear();
    finish(job({ sheets: [sheet({ id: 2 })] }));
    expect(await planning).toBeInstanceOf(PlanCancelled);
    expect(store.sheets).toEqual([]);
    expect(store.countByStatus).toEqual({});
  });

  it("الألواح الجديدة لا تدخل قائمة مصفّاة بحالة أخرى", async () => {
    vi.mocked(productionService.sheets).mockResolvedValueOnce(sheetsPage([sheet({ id: 3, status: "done" })]));
    vi.mocked(productionService.plan).mockResolvedValueOnce(job({ sheets: [sheet({ id: 2 })] }));
    const store = useProductionStore();
    await store.load("done");
    await store.plan(7);
    expect(store.sheets.map((candidate) => candidate.id)).toEqual([3]);
    expect(store.total).toBe(1);
    expect(store.countByStatus.planned).toBe(1);
  });

  it("اللوح الذي نُفِّذ أو أُتلف يخرج من تصفية «مخطَّط»", async () => {
    vi.mocked(productionService.sheets).mockResolvedValueOnce(sheetsPage([sheet(), sheet({ id: 2 })]));
    vi.mocked(productionService.recordRun).mockResolvedValueOnce(okRun);
    vi.mocked(productionService.scrap).mockResolvedValueOnce(sheet({ id: 2, status: "scrapped", placements: [] }));
    const store = useProductionStore();
    await store.load("planned");
    await store.recordRun(1, { outcome: "ok", duration_s: 200, calibration_id: null, notes: "" }, "r1");
    await store.scrap(2);
    expect(store.sheets).toEqual([]);
    expect(store.total).toBe(0);
    expect(store.countByStatus).toMatchObject({ planned: 0, done: 1, scrapped: 1 });
  });

  it("رد الكتالوج المتأخر بعد المسح لا يُكتب", async () => {
    let finish: (value: Material[]) => void = () => {};
    vi.mocked(catalogService.materials).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    const catalog = useCatalogStore();
    const loading = catalog.load();
    catalog.clear();
    finish([leather]);
    await loading;
    expect(catalog.materials).toEqual([]);
    expect(catalog.loaded).toBe(false);
    expect(catalog.loading).toBe(false);
  });
});

describe("الوصول في صفحة الإنتاج", () => {
  it("مناطق الإعلان قائمة قبل رسائلها", async () => {
    const page = await show(ProductionPage, "/production");
    expect(page.get('.plan [role="alert"]').text()).toBe("");
    expect(page.get('.plan [role="status"]').text()).toBe("");
    expect(page.get('.sheet-card [role="alert"]').text()).toBe("");
  });

  it("ينقل التركيز إلى بديل الزر الذي اختفى", async () => {
    await router.push("/production");
    await router.isReady();
    const page = mount(ProductionPage, { global: { plugins: [router] }, attachTo: document.body });
    try {
      await flushPromises();
      await button(page, "إتلاف اللوح").trigger("click");
      await flushPromises();
      expect(document.activeElement?.textContent?.trim()).toBe("تراجع");
      await button(page, "تراجع").trigger("click");
      await flushPromises();
      expect(document.activeElement?.textContent?.trim()).toBe("إتلاف اللوح");
      await button(page, "تسجيل تشغيل").trigger("click");
      await flushPromises();
      expect(document.activeElement).toBe(page.get(".run input").element);
    } finally {
      page.unmount();
    }
  });
});
