import type { Page, PageQuery } from "@/api/paging";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { ApiError } from "@/api/client";
import { routes } from "@/router";
import { catalogService, type Material, type ProductTemplate } from "@/services/catalog";
import { ordersService, type Order } from "@/services/orders";
import { useOrdersStore } from "@/stores/orders";
import OrderDetailPage from "./OrderDetailPage.vue";
import OrderNewPage from "./OrderNewPage.vue";
import OrdersPage from "./OrdersPage.vue";

vi.mock("@/services/orders", () => ({
  ordersService: { list: vi.fn(), get: vi.fn(), create: vi.fn(), transition: vi.fn() },
}));
vi.mock("@/services/catalog", () => ({
  catalogService: { materials: vi.fn(), templates: vi.fn() },
}));

const materials: Material[] = [
  {
    id: 7,
    name: "جلد نباتي",
    kind: "leather",
    thickness_mm: "2.0",
    sheet_width_mm: "600.0",
    sheet_height_mm: "305.0",
    sheet_cost: "45.00",
    supplier: "",
    notes: "",
  },
];
const templates: ProductTemplate[] = [
  {
    id: 1,
    slug: "card",
    name: "بطاقة مقوّسة",
    generator: "card",
    width_mm: "90.0",
    height_mm: "55.0",
    safe_margin_mm: "3.0",
    base_price: "25.00",
    param_schema: [{ name: "name", type: "text", label: "الاسم" }],
  },
];

function order(overrides: Partial<Order> = {}): Order {
  return {
    id: 1,
    client_ref: "ref-1",
    customer_name: "أم سارة",
    status: "draft",
    occasion_date: "2026-12-01",
    notes: "",
    total: "50.00",
    items: [
      { id: 10, template_slug: "card", material_id: 7, params: { name: "سارة" }, quantity: 2, unit_price: "25.00" },
    ],
    ...overrides,
  };
}

let router: Router;

/** خادم صغير: طلبان، والتصفية والأعداد منه كما في الخادم الحقيقي. */
function listed(query: PageQuery = {}, all: Order[] = [order(), order({ id: 2, status: "ready" })]): Page<Order> {
  const items = query.status ? all.filter((row) => row.status === query.status) : all;
  const counts: Record<string, number> = {};
  for (const row of all) counts[row.status] = (counts[row.status] ?? 0) + 1;
  return { items, count: items.length, counts };
}

async function show(component: object, path: string, props: Record<string, unknown> = {}) {
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, { props, global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  setActivePinia(createPinia());
  router = createRouter({ history: createMemoryHistory(), routes });
  vi.mocked(ordersService.list).mockReset().mockImplementation(async (query) => listed(query));
  vi.mocked(ordersService.get).mockReset().mockResolvedValue(order());
  vi.mocked(ordersService.create).mockReset();
  vi.mocked(ordersService.transition).mockReset();
  vi.mocked(catalogService.materials).mockReset().mockResolvedValue(materials);
  vi.mocked(catalogService.templates).mockReset().mockResolvedValue(templates);
});

describe("قائمة الطلبات", () => {
  it("تعرض الطلبات وتصفّي بالحالة", async () => {
    const page = await show(OrdersPage, "/orders");
    expect(page.findAll(".order")).toHaveLength(2);
    expect(page.text()).toContain("50.00 ر.ق");

    const ready = page.findAll(".chip").find((chip) => chip.text().startsWith("جاهز"));
    expect(ready!.text()).toContain("1");
    await ready!.trigger("click");
    await flushPromises();
    expect(ordersService.list).toHaveBeenLastCalledWith({ status: "ready" });
    expect(page.findAll(".order")).toHaveLength(1);
    expect(ready!.attributes("aria-pressed")).toBe("true");

    await page.findAll(".chip").find((chip) => chip.text().startsWith("ملغى"))!.trigger("click");
    await flushPromises();
    expect(page.text()).toContain("لا طلبات بهذه الحالة");
    expect(page.find(".more").exists()).toBe(false);
  });

  it("تحمّل الصفحة التالية وتعدّ من الخادم لا مما حُمّل", async () => {
    vi.mocked(ordersService.list)
      .mockResolvedValueOnce({ items: [order({ id: 3 }), order({ id: 2 })], count: 3, counts: { draft: 3 } })
      .mockResolvedValueOnce({ items: [order({ id: 2 }), order({ id: 1 })], count: 3, counts: { draft: 3 } });
    const page = await show(OrdersPage, "/orders");
    expect(page.findAll(".chip")[0].text()).toContain("3");
    expect(page.get(".more").text()).toContain("يعرض 2 من 3");
    await page.get(".more button").trigger("click");
    await flushPromises();
    expect(ordersService.list).toHaveBeenLastCalledWith({ status: "", offset: 2 });
    expect(page.findAll(".order")).toHaveLength(3);
    expect(page.find(".more").exists()).toBe(false);
  });

  it("تعرض الحالة الفارغة", async () => {
    vi.mocked(ordersService.list).mockResolvedValue(listed({}, []));
    expect((await show(OrdersPage, "/orders")).text()).toContain("لا طلبات بعد");
  });

  it("تعرض خطأ التحميل وتعيد المحاولة", async () => {
    vi.mocked(ordersService.list).mockRejectedValueOnce(new ApiError(401, "يلزم تسجيل الدخول بحساب مشرف"));
    const page = await show(OrdersPage, "/orders");
    expect(page.get('[role="alert"]').text()).toContain("يلزم تسجيل الدخول");
    await page.get(".retry").trigger("click");
    await flushPromises();
    expect(page.findAll(".order")).toHaveLength(2);
  });
});

describe("تفاصيل الطلب", () => {
  it("تعرض البنود بأسماء الكتالوج وأزرار الانتقال المتاحة", async () => {
    const page = await show(OrderDetailPage, "/orders/1", { orderId: 1 });
    expect(page.text()).toContain("بطاقة مقوّسة");
    expect(page.text()).toContain("جلد نباتي");
    expect(page.text()).toContain("الاسم");
    expect(page.findAll(".actions .btn").map((button) => button.text())).toEqual(["تأكيد الطلب", "إلغاء الطلب"]);
    expect(page.find(".order-notes").exists()).toBe(false);
  });

  it("تجلب الطلب وحده من الرابط المباشر وتعرض ملاحظاته", async () => {
    vi.mocked(ordersService.get).mockResolvedValue(order({ id: 7, notes: "تغليف هدية" }));
    const page = await show(OrderDetailPage, "/orders/7", { orderId: 7 });
    expect(ordersService.get).toHaveBeenCalledWith(7);
    expect(ordersService.list).not.toHaveBeenCalled();
    expect(page.get(".order-notes").text()).toContain("تغليف هدية");
  });

  it("لا تجلب طلبًا موجودًا في المخزن", async () => {
    useOrdersStore().orders = [order()];
    const page = await show(OrderDetailPage, "/orders/1", { orderId: 1 });
    expect(ordersService.get).not.toHaveBeenCalled();
    expect(page.text()).toContain("بطاقة مقوّسة");
  });

  it("تعرض خطأ الجلب وتعيد المحاولة", async () => {
    vi.mocked(ordersService.get).mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"));
    const page = await show(OrderDetailPage, "/orders/1", { orderId: 1 });
    expect(page.get('[role="alert"]').text()).toContain("تعذّر الاتصال بالخادم");
    await page.get(".retry").trigger("click");
    await flushPromises();
    expect(page.text()).toContain("بطاقة مقوّسة");
  });

  it("تنقل الحالة وتعرض رفض الخادم", async () => {
    vi.mocked(ordersService.transition)
      .mockRejectedValueOnce(new ApiError(409, "لا تأكيد قبل معايرة المادة من قصاصة اختبار: جلد نباتي"))
      .mockResolvedValueOnce(order({ status: "confirmed" }));
    const page = await show(OrderDetailPage, "/orders/1", { orderId: 1 });

    await page.get(".actions .primary").trigger("click");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toContain("لا تأكيد قبل معايرة المادة");

    await page.get(".actions .primary").trigger("click");
    await flushPromises();
    expect(ordersService.transition).toHaveBeenLastCalledWith(1, "confirmed");
    expect(page.find('[role="alert"]').exists()).toBe(false);
    expect(page.get(".actions .primary").text()).toBe("بدء التنفيذ");
  });

  it("الإلغاء يحتاج ضغطتين", async () => {
    vi.mocked(ordersService.transition).mockResolvedValue(order({ status: "cancelled" }));
    const page = await show(OrderDetailPage, "/orders/1", { orderId: 1 });

    await page.get(".actions .danger").trigger("click");
    expect(ordersService.transition).not.toHaveBeenCalled();
    expect(page.get(".actions .danger").text()).toContain("لتأكيد الإلغاء");

    await page.get(".actions .danger").trigger("click");
    await flushPromises();
    expect(ordersService.transition).toHaveBeenCalledWith(1, "cancelled");
    expect(page.text()).toContain("حالة نهائية");
  });

  it("تقول إن الطلب غير موجود", async () => {
    vi.mocked(ordersService.get).mockRejectedValue(new ApiError(404, "الطلب غير موجود"));
    expect((await show(OrderDetailPage, "/orders/99", { orderId: 99 })).text()).toContain("لا طلب بهذا الرقم");
  });
});

describe("طلب جديد", () => {
  it("يمنع الحفظ الناقص ويعلّم الحقول", async () => {
    const page = await show(OrderNewPage, "/orders/new");
    await page.get("form").trigger("submit");
    expect(ordersService.create).not.toHaveBeenCalled();
    expect(page.text()).toContain("اسم الزبون مطلوب");
    expect(page.text()).toContain("اختر القالب");
  });

  it("يحفظ الطلب ويفتح تفاصيله", async () => {
    vi.mocked(ordersService.create).mockResolvedValue(order({ id: 5 }));
    const page = await show(OrderNewPage, "/orders/new");

    await page.get('input[type="text"]').setValue("أم سارة");
    const [template, material] = page.findAll("select");
    await template.setValue("card");
    await material.setValue("7");
    await page.get(".params input").setValue("سارة");
    expect(page.get(".estimate").text()).toContain("25.00 ر.ق");

    await page.get("form").trigger("submit");
    await flushPromises();

    expect(ordersService.create).toHaveBeenCalledTimes(1);
    const draft = vi.mocked(ordersService.create).mock.calls[0][0];
    expect(draft).toMatchObject({
      customer_name: "أم سارة",
      items: [{ template_slug: "card", material_id: 7, params: { name: "سارة" }, quantity: 1, unit_price: null }],
    });
    expect(draft.client_ref).toMatch(/^[0-9a-f-]{36}$/);
    expect(router.currentRoute.value.fullPath).toBe("/orders/5");
    expect(useOrdersStore().byId(5)).toBeDefined();
  });

  it("يعيد الإرسال بالمفتاح نفسه بعد فشل", async () => {
    vi.mocked(ordersService.create)
      .mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"))
      .mockResolvedValueOnce(order({ id: 5 }));
    const page = await show(OrderNewPage, "/orders/new");
    await page.get('input[type="text"]').setValue("أم سارة");
    const [template, material] = page.findAll("select");
    await template.setValue("card");
    await material.setValue("7");
    await page.get(".params input").setValue("سارة");

    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toContain("تعذّر الاتصال بالخادم");

    await page.get("form").trigger("submit");
    await flushPromises();
    const [first, second] = vi.mocked(ordersService.create).mock.calls;
    expect(second[0].client_ref).toBe(first[0].client_ref);
  });

  it("حدثان في النبضة نفسها لا يمحو أحدهما الآخر", async () => {
    vi.mocked(ordersService.create).mockResolvedValue(order({ id: 5 }));
    const page = await show(OrderNewPage, "/orders/new");
    await page.get('input[type="text"]').setValue("أم سارة");
    const [template, material] = page.findAll("select");
    await template.setValue("card");
    await material.setValue("7");

    // بلا await بين الحدثين: كما تفعل التعبئة التلقائية في المتصفح.
    const name = page.get(".params input").element as HTMLInputElement;
    const quantity = page.get('fieldset input[type="number"]').element as HTMLInputElement;
    name.value = "سارة";
    name.dispatchEvent(new Event("input"));
    quantity.value = "4";
    quantity.dispatchEvent(new Event("input"));

    await page.get("form").trigger("submit");
    await flushPromises();
    expect(vi.mocked(ordersService.create).mock.calls[0][0].items[0]).toMatchObject({
      params: { name: "سارة" },
      quantity: 4,
    });
  });

  it("يضيف بندًا ويحذفه", async () => {
    const page = await show(OrderNewPage, "/orders/new");
    expect(page.find(".remove").exists()).toBe(false);
    await page.findAll("form > .btn")[0].trigger("click");
    expect(page.findAll("fieldset")).toHaveLength(2);
    await page.findAll(".remove")[0].trigger("click");
    expect(page.findAll("fieldset")).toHaveLength(1);
  });

  it("يشرح حين يخلو الكتالوج", async () => {
    vi.mocked(catalogService.templates).mockResolvedValue([]);
    expect((await show(OrderNewPage, "/orders/new")).text()).toContain("قبل تعريف قالب واحد ومادة واحدة");
  });
});
