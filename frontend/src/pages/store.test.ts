import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { ApiError } from "@/api/client";
import { installLocale } from "@/i18n/router";
import { routes } from "@/router";
import { sessionService } from "@/services/session";
import {
  storeService,
  type Cart,
  type CartItem,
  type Preview,
  type StoreTemplate,
  type StoreTemplateDetail,
  type Tracking,
} from "@/services/store";
import { useCartStore } from "@/stores/cart";
import CartPage from "./CartPage.vue";
import CheckoutPage from "./CheckoutPage.vue";
import PolicyPage from "./PolicyPage.vue";
import ProductPage from "./ProductPage.vue";
import ProductsPage from "./ProductsPage.vue";
import TestPayPage from "./TestPayPage.vue";
import TrackPage from "./TrackPage.vue";

vi.mock("@/services/store", () => ({
  storeService: {
    templates: vi.fn(),
    template: vi.fn(),
    limits: vi.fn(),
    preview: vi.fn(),
    cart: vi.fn(),
    addItem: vi.fn(),
    setQuantity: vi.fn(),
    removeItem: vi.fn(),
    checkout: vi.fn(),
    zones: vi.fn(),
    track: vi.fn(),
    pickupSlots: vi.fn(),
    bookPickup: vi.fn(),
    simulatePayment: vi.fn(),
  },
}));
vi.mock("@/services/session", () => ({
  sessionService: { me: vi.fn(), login: vi.fn(), logout: vi.fn() },
}));

const plaque: StoreTemplate = {
  slug: "name-plaque",
  name: "لوحة اسم",
  name_en: "Name plaque",
  description: "لوحة خشب باسمك",
  description_en: "A wooden plaque with your name",
  width_mm: "200.0",
  height_mm: "80.0",
  base_price: "120.00",
  allows_religious_text: false,
  fields: [
    { name: "الاسم", label: "الاسم", label_en: "Name", type: "text", max_length: 20 },
    { name: "الخط", label: "الخط", label_en: "Font", type: "choice", choices: ["كايرو", "المراي"], choices_en: ["Cairo", "Almarai"] },
  ],
};
const detail: StoreTemplateDetail = {
  ...plaque,
  materials: [
    { id: 3, name: "خشب زان", name_en: "Beech", kind: "wood", thickness_mm: "3.00" },
    { id: 4, name: "أكريليك", name_en: "Acrylic", kind: "acrylic", thickness_mm: "3.00" },
  ],
};
const rendered: Preview = {
  svg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
  sha256: "a".repeat(64),
  width_mm: 200,
  height_mm: 80,
  needs_review: false,
  review_reasons: [],
  text_sizes: { الاسم: 12 },
};
const line: CartItem = {
  id: 9,
  template_slug: "name-plaque",
  name: "لوحة اسم",
  name_en: "Name plaque",
  material_id: 3,
  material_name: "خشب زان",
  material_name_en: "Beech",
  params: { الاسم: "نورة", الخط: "كايرو" },
  quantity: 2,
  unit_price: "120.00",
  line_total: "240.00",
  needs_review: false,
};

function cartOf(overrides: Partial<Cart> = {}): Cart {
  return {
    status: "draft",
    items: [line],
    subtotal: "240.00",
    delivery_fee: "0.00",
    total: "240.00",
    currency: "QAR",
    ready_on: "2026-11-28",
    needs_review: false,
    payment_url: null,
    ...overrides,
  };
}
const emptyCart = cartOf({ status: "empty", items: [], subtotal: "0", total: "0", ready_on: null });

function tracking(overrides: Partial<Tracking> = {}): Tracking {
  return {
    status: "ready",
    status_label: "جاهز",
    fulfillment: "pickup",
    steps: [
      { status: "paid", label: "مدفوع", reached: true, at: "2026-11-21T15:00:00+03:00" },
      { status: "ready", label: "جاهز", reached: true, at: null },
      { status: "delivered", label: "مُسلَّم", reached: false, at: null },
    ],
    items: [{ name: "لوحة اسم", name_en: "Name plaque", material_name: "خشب زان", material_name_en: "Beech", quantity: 2, line_total: "240.00" }],
    subtotal: "240.00",
    delivery_fee: "0.00",
    total: "240.00",
    currency: "QAR",
    occasion_date: null,
    delivery_zone: null,
    pickup: null,
    can_book_pickup: true,
    updated_at: "2026-11-21T15:00:00+03:00",
    ...overrides,
  };
}

function rejection(status: number, body: Record<string, unknown>): ApiError {
  return new ApiError(status, String(body.detail ?? ""), body);
}

let router: Router;

beforeEach(() => {
  setActivePinia(createPinia());
  router = createRouter({ history: createMemoryHistory(), routes });
  installLocale(router);
  for (const mock of Object.values(storeService)) vi.mocked(mock).mockReset();
  vi.mocked(storeService.templates).mockResolvedValue([plaque]);
  vi.mocked(storeService.template).mockResolvedValue(detail);
  vi.mocked(storeService.limits).mockResolvedValue([
    { field: "الاسم", when: { الخط: "كايرو" }, max_chars: 12, min_text_height_mm: 3 },
    { field: "الاسم", when: { الخط: "المراي" }, max_chars: 4, min_text_height_mm: 3.4 },
  ]);
  vi.mocked(storeService.preview).mockResolvedValue(rendered);
  vi.mocked(storeService.cart).mockResolvedValue(cartOf());
  vi.mocked(storeService.zones).mockResolvedValue([{ id: 2, name: "اللؤلؤة", name_en: "The Pearl", fee: "25.00" }]);
  vi.mocked(sessionService.me).mockReset().mockResolvedValue(null);
});

afterEach(() => {
  vi.useRealTimers();
});

async function show(component: object, path: string, props: Record<string, unknown> = {}) {
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, { props, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}

function button(page: ReturnType<typeof mount>, text: string) {
  const found = page.findAll("button").find((candidate) => candidate.text() === text);
  if (!found) throw new Error(`لا زر بنص «${text}»`);
  return found;
}

/** يكتب في حقل الاسم وينتظر مهلة المعاينة وردّها. */
async function typeName(page: ReturnType<typeof mount>, text: string): Promise<void> {
  await page.get('input[name="الاسم"]').setValue(text);
  await vi.advanceTimersByTimeAsync(400);
  await flushPromises();
}

describe("صفحة المنتجات", () => {
  it("تعرض كل منتج باسمه وسعره ورابط مصمِّمه", async () => {
    const page = await show(ProductsPage, "/products");
    const card = page.get("a.product-card");
    expect(card.text()).toContain("لوحة اسم");
    expect(card.text()).toContain("120.00 ر.ق");
    expect(card.text()).toContain("200 × 80 مم");
    expect(card.attributes("href")).toBe("/products/name-plaque");
    page.unmount();
  });

  it("بالإنجليزية تعرض الاسم الإنجليزي ويبقى الرابط تحت /en", async () => {
    const page = await show(ProductsPage, "/en/products");
    const card = page.get("a.product-card");
    expect(card.text()).toContain("Name plaque");
    expect(card.attributes("href")).toBe("/en/products/name-plaque");
    page.unmount();
  });

  it("تعرض خطأ التحميل وتعيد المحاولة", async () => {
    vi.mocked(storeService.templates).mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال"));
    const page = await show(ProductsPage, "/products");
    expect(page.get('[role="alert"]').text()).toContain("تعذّر الاتصال");
    await button(page, "إعادة المحاولة").trigger("click");
    await flushPromises();
    expect(page.find("a.product-card").exists()).toBe(true);
    page.unmount();
  });
});

describe("المصمِّم", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("لا يطلب المعاينة قبل ملء المطلوب، ثم يعرضها صورةً بعد الكتابة", async () => {
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    expect(page.get("h1").text()).toBe("لوحة اسم");
    expect(storeService.preview).not.toHaveBeenCalled();
    expect(page.find(".canvas img").exists()).toBe(false);

    await typeName(page, "  نورة ");
    // أول خيار للخط مختار، والنص يُرسل مطويّ الفراغات مع الخامة الأولى ولغة الصفحة.
    expect(storeService.preview).toHaveBeenCalledWith("name-plaque", 3, { الاسم: "نورة", الخط: "كايرو" }, "ar");
    expect(page.get(".canvas img").attributes("src")).toMatch(/^data:image\/svg\+xml/);
    expect(page.text()).toContain("4 من 12");
    page.unmount();
  });

  it("كتابة متتابعة تطلب معاينة واحدة لآخر نص", async () => {
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    await page.get('input[name="الاسم"]').setValue("نو");
    await vi.advanceTimersByTimeAsync(100);
    await typeName(page, "نورة");
    expect(storeService.preview).toHaveBeenCalledTimes(1);
    expect(vi.mocked(storeService.preview).mock.calls[0][2]).toEqual({ الاسم: "نورة", الخط: "كايرو" });
    page.unmount();
  });

  it("الإضافة تشترط الإقرار، وتحمل بصمة المعاينة، ثم تفتح السلة", async () => {
    vi.mocked(storeService.addItem).mockResolvedValue(cartOf());
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    await typeName(page, "نورة");
    const add = button(page, "أضف إلى السلة");
    expect(add.attributes("disabled")).toBeDefined();

    await page.get('input[name="acknowledged"]').setValue(true);
    expect(add.attributes("disabled")).toBeUndefined();
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(storeService.addItem).toHaveBeenCalledWith(
      { template_slug: "name-plaque", material_id: 3, params: { الاسم: "نورة", الخط: "كايرو" }, quantity: 1, sha256: rendered.sha256, acknowledged: true },
      "ar",
    );
    expect(router.currentRoute.value.name).toBe("cart");
    page.unmount();
  });

  it("تغيير النص بعد الإقرار يُسقطه", async () => {
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    await typeName(page, "نورة");
    const acknowledged = page.get<HTMLInputElement>('input[name="acknowledged"]');
    await acknowledged.setValue(true);
    await typeName(page, "نورا");
    expect(acknowledged.element.checked).toBe(false);
    page.unmount();
  });

  it("رفض النص الديني يظهر عند حقله مع المنتجات المقترحة", async () => {
    vi.mocked(storeService.templates).mockResolvedValue([plaque, { ...plaque, slug: "wall-art", name: "لوحة معلّقة", allows_religious_text: true }]);
    vi.mocked(storeService.preview).mockRejectedValue(
      rejection(422, {
        code: "invalid",
        detail: "راجع الحقول المحدّدة",
        fields: { الاسم: { code: "religious_not_allowed", message: "نحفر النصوص الدينية على ما يُعلَّق ويُصان فقط" } },
        suggestions: ["wall-art"],
      }),
    );
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    await typeName(page, "بسم الله");
    expect(page.find(".canvas img").exists()).toBe(false);
    expect(page.get('input[name="الاسم"]').attributes("aria-invalid")).toBe("true");
    expect(page.get(".field .error").text()).toBe("نحفر النصوص الدينية على ما يُعلَّق ويُصان فقط");
    const suggestion = page.get(".suggest a");
    expect(suggestion.text()).toBe("لوحة معلّقة");
    expect(suggestion.attributes("href")).toBe("/products/wall-art");
    expect(page.get<HTMLInputElement>('input[name="acknowledged"]').element.disabled).toBe(true);
    page.unmount();
  });

  it("رفض الإضافة لتغيّر المعاينة يُسقط الإقرار ويعيد رسمها", async () => {
    vi.mocked(storeService.addItem).mockRejectedValue(rejection(422, { code: "preview_mismatch", detail: "المعاينة تغيّرت؛ حدّثها ثم أضف المنتج" }));
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    await typeName(page, "نورة");
    await page.get('input[name="acknowledged"]').setValue(true);
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toBe("المعاينة تغيّرت؛ حدّثها ثم أضف المنتج");
    expect(page.get<HTMLInputElement>('input[name="acknowledged"]').element.checked).toBe(false);
    await vi.advanceTimersByTimeAsync(400);
    expect(storeService.preview).toHaveBeenCalledTimes(2);
    expect(router.currentRoute.value.name).toBe("product");
    page.unmount();
  });

  it("منتج بلا خامة معروضة يُعلن ذلك ولا يعرض نموذجًا", async () => {
    vi.mocked(storeService.template).mockResolvedValue({ ...detail, materials: [] });
    const page = await show(ProductPage, "/products/name-plaque", { slug: "name-plaque" });
    expect(page.get('[role="alert"]').text()).toBe("هذا المنتج غير متاح للتصميم الآن.");
    expect(page.find("form").exists()).toBe(false);
    page.unmount();
  });
});

describe("السلة", () => {
  it("تعرض البنود والمجموع وأقرب جاهزية", async () => {
    const page = await show(CartPage, "/cart");
    expect(page.get(".line").text()).toContain("نورة · كايرو");
    expect(page.get(".sums .grand").text()).toContain("240.00 ر.ق");
    expect(page.text()).toContain("أقرب جاهزية: السبت، 28 نوفمبر");
    expect(page.get('a[href="/checkout"]').text()).toBe("إتمام الطلب");
    page.unmount();
  });

  it("الفارغة تدعو إلى المنتجات", async () => {
    vi.mocked(storeService.cart).mockResolvedValue(emptyCart);
    const page = await show(CartPage, "/cart");
    expect(page.text()).toContain("سلتك فارغة.");
    expect(page.get(".empty a").attributes("href")).toBe("/products");
    page.unmount();
  });

  it("تغيّر الكمية وتحذف البند عبر الخادم", async () => {
    vi.mocked(storeService.setQuantity).mockResolvedValue(cartOf({ items: [{ ...line, quantity: 3, line_total: "360.00" }], subtotal: "360.00", total: "360.00" }));
    vi.mocked(storeService.removeItem).mockResolvedValue(emptyCart);
    const page = await show(CartPage, "/cart");
    await page.get(".qty input").setValue(3);
    await page.get(".qty input").trigger("change");
    await flushPromises();
    expect(storeService.setQuantity).toHaveBeenCalledWith(9, 3, "ar");
    expect(page.get(".sums .grand").text()).toContain("360.00 ر.ق");

    await button(page, "حذف").trigger("click");
    await flushPromises();
    expect(storeService.removeItem).toHaveBeenCalledWith(9, "ar");
    expect(page.text()).toContain("سلتك فارغة.");
    page.unmount();
  });

  it("كمية خارج المدى لا تُرسل ويعود الحقل إلى قيمته", async () => {
    const page = await show(CartPage, "/cart");
    const input = page.get<HTMLInputElement>(".qty input");
    await input.setValue(0);
    await input.trigger("change");
    expect(storeService.setQuantity).not.toHaveBeenCalled();
    expect(input.element.value).toBe("2");
    page.unmount();
  });

  it("رفض الخادم يُعرض وتُعاد السلة كما هي عنده", async () => {
    vi.mocked(storeService.setQuantity).mockRejectedValue(rejection(409, { code: "cart_locked", detail: "فُتحت صفحة الدفع لهذه السلة" }));
    const page = await show(CartPage, "/cart");
    await page.get(".qty input").setValue(5);
    await page.get(".qty input").trigger("change");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toBe("فُتحت صفحة الدفع لهذه السلة");
    expect(storeService.cart).toHaveBeenCalledTimes(2);
    page.unmount();
  });

  it("المقفلة بانتظار الدفع لا تُعدَّل وتعرض رابط الدفع الآمن وحده", async () => {
    vi.mocked(storeService.cart).mockResolvedValue(cartOf({ status: "awaiting_payment", payment_url: "/checkout/test-pay/test_ab" }));
    const page = await show(CartPage, "/cart");
    expect(page.get(".locked a").attributes("href")).toBe("/checkout/test-pay/test_ab");
    expect(page.get<HTMLInputElement>(".qty input").element.disabled).toBe(true);
    expect(page.find('a[href="/checkout"]').exists()).toBe(false);
    page.unmount();

    vi.mocked(storeService.cart).mockResolvedValue(cartOf({ status: "awaiting_payment", payment_url: "javascript:alert(1)" }));
    setActivePinia(createPinia());
    const unsafe = await show(CartPage, "/cart");
    expect(unsafe.find(".locked a").exists()).toBe(false);
    unsafe.unmount();
  });
});

describe("إتمام الطلب", () => {
  const result = {
    payment_url: "/checkout/test-pay/test_ab",
    amount: "265.00",
    currency: "QAR",
    expires_at: "2026-11-21T19:30:00+03:00",
    tracking_token: "tok_secret",
  };

  it("يشترط الاسم، ومنطقة التوصيل مع التوصيل، قبل أي نداء", async () => {
    const page = await show(CheckoutPage, "/checkout");
    await page.get("form").trigger("submit");
    expect(page.get('input[name="customer_name"]').attributes("aria-invalid")).toBe("true");

    await page.get('input[name="customer_name"]').setValue("نورة");
    await page.get('input[value="delivery"]').setValue(true);
    await page.get("form").trigger("submit");
    expect(page.get('select[name="delivery_zone_id"]').attributes("aria-invalid")).toBe("true");
    expect(storeService.checkout).not.toHaveBeenCalled();
    page.unmount();
  });

  it("التوصيل يضيف رسم المنطقة إلى الإجمالي ويُرسل معرّفها", async () => {
    vi.mocked(storeService.checkout).mockResolvedValue(result);
    const page = await show(CheckoutPage, "/checkout");
    await page.get('input[name="customer_name"]').setValue("  نورة   علي ");
    await page.get('input[value="delivery"]').setValue(true);
    await page.get('select[name="delivery_zone_id"]').setValue(2);
    expect(page.get(".summary .grand").text()).toContain("265.00 ر.ق");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(storeService.checkout).toHaveBeenCalledWith(
      { customer_name: "نورة علي", fulfillment: "delivery", occasion_date: null, notes: "", source: "", delivery_zone_id: 2 },
      "ar",
    );
    page.unmount();
  });

  it("بعد فتح الدفع يسلّم رابط التتبّع ورابط الدفع", async () => {
    vi.mocked(storeService.checkout).mockResolvedValue(result);
    const page = await show(CheckoutPage, "/en/checkout");
    await page.get('input[name="customer_name"]').setValue("Noura");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get("h1").text()).toBe("Payment is next");
    expect(page.get("a.pay").attributes("href")).toBe("/checkout/test-pay/test_ab");
    expect(page.get<HTMLInputElement>('input[name="tracking-link"]').element.value).toBe(`${window.location.origin}/en/track/tok_secret`);
    expect(page.get('a[href="/en/track/tok_secret"]').text()).toBe("Tracking page");
    // الاستلام بموعد بلا منطقة، ولغة الصفحة تُرسل لتُكتب على العميل.
    expect(vi.mocked(storeService.checkout).mock.calls[0]).toEqual([
      { customer_name: "Noura", fulfillment: "pickup", occasion_date: null, notes: "", source: "", delivery_zone_id: null },
      "en",
    ]);
    page.unmount();
  });

  it("تاريخ مناسبة لا نلحقه يُرفض مع أقرب جاهزية", async () => {
    vi.mocked(storeService.checkout).mockRejectedValue(
      rejection(422, { code: "occasion_too_soon", detail: "لا نلحق تاريخ المناسبة؛ أقرب جاهزية مذكورة", ready_on: "2026-12-05" }),
    );
    const page = await show(CheckoutPage, "/checkout");
    await page.get('input[name="customer_name"]').setValue("نورة");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toBe("لا نلحق تاريخ المناسبة؛ أقرب جاهزية مذكورة");
    expect(page.get(".summary .ready").text()).toBe("أقرب جاهزية: السبت، 5 ديسمبر");
    page.unmount();
  });

  it("بلا مناطق مفعَّلة يُعطَّل التوصيل بسببه الظاهر", async () => {
    vi.mocked(storeService.zones).mockResolvedValue([]);
    const page = await show(CheckoutPage, "/checkout");
    expect(page.get<HTMLInputElement>('input[value="delivery"]').element.disabled).toBe(true);
    expect(page.text()).toContain("التوصيل غير متاح الآن.");
    page.unmount();
  });

  it("السلة الفارغة لا تعرض نموذجًا", async () => {
    vi.mocked(storeService.cart).mockResolvedValue(emptyCart);
    const page = await show(CheckoutPage, "/checkout");
    expect(page.find("form").exists()).toBe(false);
    expect(page.text()).toContain("لا شيء في السلة لإتمامه.");
    page.unmount();
  });
});

describe("تتبّع الطلب", () => {
  it("رابط لا طلب له يُعلن ذلك بلا تفاصيل", async () => {
    vi.mocked(storeService.track).mockRejectedValue(rejection(404, { code: "order_not_found", detail: "الطلب غير موجود" }));
    const page = await show(TrackPage, "/track/nope", { token: "nope" });
    expect(page.text()).toContain("لا طلب بهذا الرابط.");
    expect(page.find(".steps").exists()).toBe(false);
    page.unmount();
  });

  it("يعرض الخطوات والمحتويات، ويحجز موعد الاستلام", async () => {
    const slot = "2026-11-28T16:00:00+03:00";
    vi.mocked(storeService.track).mockResolvedValue(tracking());
    vi.mocked(storeService.pickupSlots).mockResolvedValue({ slot_min: 30, days: [{ day: "2026-11-28", slots: [slot] }] });
    vi.mocked(storeService.bookPickup).mockResolvedValue(
      tracking({ status: "ready_for_pickup", status_label: "جاهز للاستلام", pickup: { starts_at: slot, ends_at: "2026-11-28T16:30:00+03:00" } }),
    );
    const page = await show(TrackPage, "/track/tok", { token: "tok" });
    expect(storeService.track).toHaveBeenCalledWith("tok", "ar");
    expect(page.findAll(".steps li.reached")).toHaveLength(2);
    expect(page.get('.steps li[aria-current="step"]').text()).toContain("جاهز");
    expect(page.text()).toContain("لوحة اسم، خشب زان");

    await page.get(".day .chip").trigger("click");
    await flushPromises();
    expect(storeService.bookPickup).toHaveBeenCalledWith("tok", slot, "ar");
    expect(page.get(".booked").text()).toContain("موعدك:");
    expect(page.find(".day").exists()).toBe(false);
    expect(button(page, "تغيير الموعد").exists()).toBe(true);
    page.unmount();
  });

  it("موعد سُبق إليه يُعلن وتُحدَّث المواعيد", async () => {
    vi.mocked(storeService.track).mockResolvedValue(tracking());
    vi.mocked(storeService.pickupSlots).mockResolvedValue({ slot_min: 30, days: [{ day: "2026-11-28", slots: ["2026-11-28T16:00:00+03:00"] }] });
    vi.mocked(storeService.bookPickup).mockRejectedValue(rejection(409, { code: "slot_taken", detail: "سبقك أحد إلى هذا الموعد؛ اختر موعدًا آخر" }));
    const page = await show(TrackPage, "/track/tok", { token: "tok" });
    await page.get(".day .chip").trigger("click");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toBe("سبقك أحد إلى هذا الموعد؛ اختر موعدًا آخر");
    expect(storeService.pickupSlots).toHaveBeenCalledTimes(2);
    page.unmount();
  });

  it("طلب التوصيل بلا قسم استلام، وقبل الجاهزية لا مواعيد", async () => {
    vi.mocked(storeService.track).mockResolvedValue(
      tracking({ fulfillment: "delivery", can_book_pickup: false, delivery_zone: { name: "اللؤلؤة", name_en: "The Pearl" }, delivery_fee: "25.00", total: "265.00" }),
    );
    const delivery = await show(TrackPage, "/track/tok", { token: "tok" });
    expect(delivery.find(".pickup").exists()).toBe(false);
    expect(delivery.text()).toContain("التوصيل إلى: اللؤلؤة");
    expect(storeService.pickupSlots).not.toHaveBeenCalled();
    delivery.unmount();

    vi.mocked(storeService.track).mockResolvedValue(tracking({ status: "paid", status_label: "مدفوع", can_book_pickup: false }));
    const early = await show(TrackPage, "/track/tok2", { token: "tok2" });
    expect(early.get(".pickup").text()).toContain("يُفتح حجز الموعد حين يجهز الطلب.");
    early.unmount();
  });
});

describe("صفحات الثقة والدفع التجريبي", () => {
  it("صفحة الأسئلة تعرض سياسة النص الديني بلغة الصفحة", async () => {
    const arabic = await show(PolicyPage, "/faq", { topic: "faq" });
    expect(arabic.get("h1").text()).toBe("الأسئلة الشائعة");
    expect(arabic.findAll("section")).toHaveLength(6);
    expect(arabic.text()).toContain("هل تحفرون النصوص الدينية؟");
    arabic.unmount();
    const english = await show(PolicyPage, "/en/returns", { topic: "returns" });
    expect(english.get("h1").text()).toBe("Returns and cancellation");
    expect(english.findAll("section")).toHaveLength(4);
    english.unmount();
  });

  it("مسارات الثقة كلها معرَّفة بلغتين", async () => {
    for (const topic of ["faq", "returns", "privacy", "terms"]) {
      await router.push(`/en/${topic}`);
      expect(router.currentRoute.value.name).toBe(topic);
      expect(router.currentRoute.value.meta.localized).toBe(true);
    }
  });

  it("الدفع التجريبي: الزائر لا يحاكي، والمشرف يرسل الإشعار", async () => {
    const guest = await show(TestPayPage, "/checkout/test-pay/test_ab", { sessionId: "test_ab" });
    expect(guest.text()).toContain("المحاكاة لحسابات المشرفين.");
    expect(guest.findAll("button")).toHaveLength(0);
    guest.unmount();

    setActivePinia(createPinia());
    vi.mocked(sessionService.me).mockResolvedValue({ id: 1, username: "staff", is_staff: true, admin_url: "/admin/" });
    vi.mocked(storeService.simulatePayment).mockResolvedValue({ ok: true, outcome: "paid" });
    const staff = await show(TestPayPage, "/checkout/test-pay/test_ab", { sessionId: "test_ab" });
    await button(staff, "نجح الدفع").trigger("click");
    await flushPromises();
    expect(storeService.simulatePayment).toHaveBeenCalledWith("test_ab", "captured");
    expect(staff.get('[role="status"]').text()).toBe("وصل الإشعار: paid");
    staff.unmount();
  });
});

describe("تنقّل القشرة", () => {
  async function shell(path: string) {
    const { default: App } = await import("@/App.vue");
    await router.push(path);
    const app = mount(App, { global: { plugins: [router] }, attachTo: document.body });
    await flushPromises();
    return app;
  }

  it("الزائر يرى المتجر وعدد ما في سلته وروابط الثقة، لا أقسام الورشة", async () => {
    const app = await shell("/products");
    const main = app.get("nav.main");
    expect(main.findAll("a").map((link) => link.attributes("href"))).toEqual(["/products", "/cart"]);
    expect(main.get(".count").text()).toBe("2");
    expect(useCartStore().count).toBe(2);
    expect(app.get("nav.store-foot").findAll("a").map((link) => link.attributes("href"))).toEqual(["/faq", "/returns", "/privacy", "/terms"]);
    app.unmount();
  });

  it("المشرف يرى أقسام الورشة ورابطًا إلى المتجر", async () => {
    vi.mocked(sessionService.me).mockResolvedValue({ id: 1, username: "staff", is_staff: true, admin_url: "/admin/" });
    const app = await shell("/products");
    expect(app.get("nav.main").findAll("a").map((link) => link.attributes("href"))).toEqual(["/orders", "/production", "/materials", "/templates"]);
    expect(app.find("nav.store-foot").exists()).toBe(false);
    expect(app.get('nav.aux a[href="/products"]').text()).toBe("المتجر");
    app.unmount();
  });
});
