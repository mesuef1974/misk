// يقارن صفحات المنصة بشاشات دليل الهوية brand/misk/identity/screens (app-light، app-dark، mobile، landing، print).
// كل شاشة تُصيَّر من ملفها في الدليل، والصفحة المقابلة تُصيَّر بالمقاس والوضع نفسيهما، ثم تُقارن القياسات
// المحسوبة لعناصرهما المتقابلة: الأبعاد والحواف والألوان والخطوط. المحتوى يختلف (الدليل نموذج والصفحة بيانات)،
// فلا مقارنة بكسلات. الخادم مزيَّف هنا: Vite يخدم الواجهة و/api/ يُجاب من هذا الملف.
import { readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const SCREENS = path.resolve(import.meta.dirname, "../../brand/misk/identity/screens");

/** [الوصف، محدِّد عنصر الدليل، محدِّد عنصر الصفحة، الخصائص المقارَنة]. width وheight من المستطيل المرسوم،
 *  و«أ>ب» تقارن خاصية «أ» في الدليل بخاصية «ب» في الصفحة. */
type Pair = [label: string, guide: string, app: string, props: string[]];

const SURFACE = ["background-color", "border-top-color", "border-top-width", "border-top-left-radius"];
const TEXT = ["font-family", "font-size", "font-weight", "color"];

const SHELL = `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>مسك</title>
<script type="module" src="/static/@vite/client"></script>
<script type="module" src="/static/src/main.ts"></script></head><body><div id="app"></div></body></html>`;

const MATERIAL = {
  id: 1, name: "جلد نباتي طبيعي", kind: "leather", thickness_mm: "2.00", sheet_width_mm: "600.0",
  sheet_height_mm: "305.0", sheet_cost: "180.00", supplier: "", notes: "",
};
const TEMPLATE = {
  id: 1, slug: "case-iphone-17", name: "كفر جلد آيفون 17", generator: "case_name", width_mm: "72.0",
  height_mm: "150.0", safe_margin_mm: "3.0", base_price: "85.00",
  param_schema: [{ name: "name", type: "text", label: "الاسم", max_length: 20 }],
};
const ORDERS = ["ready", "draft", "delivered"].map((status, index) => ({
  id: index + 1, client_ref: `ref-${index}`, customer_name: `عميل ${index + 1}`, status, occasion_date: "2026-12-01",
  notes: "", total: "170.00",
  items: [{ id: index + 1, template_slug: TEMPLATE.slug, material_id: 1, params: { name: "نورة" }, quantity: 2, unit_price: "85.00" }],
}));

interface AppState {
  staff?: boolean;
  orders?: typeof ORDERS;
  /** الطلبات تفشل بلا وصول إلى الخادم، لعرض التنبيه. */
  offline?: boolean;
}

function viewportOf(screen: string): { width: number; height: number } {
  const html = readFileSync(path.join(SCREENS, `${screen}.html`), "utf-8");
  const size = /html,body\{margin:0;inline-size:(\d+)px;block-size:(\d+)px/.exec(html);
  if (!size) throw new Error(`لا مقاس في ${screen}.html`);
  return { width: Number(size[1]), height: Number(size[2]) };
}

async function openApp(page: Page, route: string, state: AppState = {}): Promise<void> {
  const { staff = true, orders = ORDERS, offline = false } = state;
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*", async (request) => {
    const url = new URL(request.request().url());
    if (url.pathname.startsWith("/static/")) return request.continue();
    if (!url.pathname.startsWith("/api/")) return request.fulfill({ contentType: "text/html", body: SHELL });
    if (url.pathname === "/api/ping") return request.fulfill(json({ ok: true, site: "مسك" }));
    if (url.pathname === "/api/me") {
      return request.fulfill(
        staff ? json({ id: 1, username: "مشرف", is_staff: true, admin_url: null }) : json({ detail: "لا جلسة" }, 401),
      );
    }
    if (url.pathname === "/api/orders") {
      if (offline) return request.abort();
      return request.fulfill(json({ items: orders, count: orders.length, counts: {} }));
    }
    if (url.pathname === "/api/catalog/materials") return request.fulfill(json([MATERIAL]));
    if (url.pathname === "/api/catalog/templates") return request.fulfill(json([TEMPLATE]));
    if (url.pathname === "/api/production/sheets") return request.fulfill(json({ items: [], count: 0, counts: {} }));
    return request.fulfill(json({ detail: "غير موجود" }, 404));
  });
  await page.goto(route);
  await page.locator("main.wrap").waitFor();
  await page.evaluate(() => document.fonts.ready);
}

async function measure(page: Page, selector: string, props: string[]): Promise<Record<string, string>> {
  const element = page.locator(selector).first();
  await element.waitFor({ state: "attached" });
  return element.evaluate((node, names) => {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    const out: Record<string, string> = {};
    for (const name of names) {
      if (name === "width" || name === "height") out[name] = `${box[name]}px`;
      else if (name === "font-family") out[name] = style.fontFamily.split(",")[0].replace(/["']/g, "").trim();
      else out[name] = style.getPropertyValue(name);
    }
    return out;
  }, props);
}

/** الأطوال تتطابق في حدود بكسل واحد (تقريب المتصفح)، وما عداها حرفيًّا. */
function same(guide: string, app: string): boolean {
  const px = /^(-?[\d.]+)px$/;
  const a = px.exec(guide);
  const b = px.exec(app);
  return a && b ? Math.abs(Number(a[1]) - Number(b[1])) <= 1 : guide === app;
}

async function compare(guide: Page, app: Page, pairs: Pair[], known: string[] = []): Promise<void> {
  for (const [label, guideSelector, appSelector, props] of pairs) {
    const sides = props.map((prop) => (prop.includes(">") ? prop.split(">") : [prop, prop]));
    const expected = await measure(guide, guideSelector, sides.map(([left]) => left));
    const actual = await measure(app, appSelector, sides.map(([, right]) => right));
    for (const [left, right] of sides) {
      if (known.includes(`${label} — ${left}`)) continue;
      expect.soft(same(expected[left], actual[right]), `${label} — ${left}: الدليل ${expected[left]}، الصفحة ${actual[right]}`).toBe(true);
    }
  }
}

/** أعمدة الهيكل مرتّبة بعرضها: الشريط الجانبي والمحتوى. */
async function tracks(page: Page, selector: string): Promise<number[]> {
  const columns = await page.locator(selector).first().evaluate((node) => getComputedStyle(node).gridTemplateColumns);
  return columns.split(" ").map(parseFloat).sort((a, b) => a - b);
}

// فروق معروفة عن شاشات الدليل، لكلٍّ سببه:
// - شاشتا app-light وapp-dark تضعان الشريط الجانبي في العمود العريض والمحتوى في عمود 280 (ترتيب العمودين
//   معكوس في ملف الدليل نفسه)، فحدّ الشريط فيهما عند طرف الصفحة، والزر يلتفّ نصه. الصفحة تجعل الشريط 280
//   وحدّه جهة المحتوى؛ فيُقارن عرضا العمودين وحدّ الشريط أيًّا كانت جهته، وارتفاع الزر يُقارن في landing.
// - زر app-dark بلون brand الداكن، و--accent الليلي في token_map (ADOPTION.yaml) هو brand-strong:
//   الصفحة تتبع token_map الذي يفرضه tests/test_brand.py.
const KNOWN: Record<string, string[]> = { "app-dark": ["الزر الأساسي — background-color"] };

async function openGuide(page: Page, screen: string): Promise<void> {
  await page.goto(pathToFileURL(path.join(SCREENS, `${screen}.html`)).href);
  await page.evaluate(() => document.fonts.ready);
}

const BODY: Pair = ["النص الأساسي", "body", "body", ["background-color", "color", "font-family", "font-size", "line-height"]];

/** هيكل التطبيق وقائمته: الشريط الجانبي، رأس الصفحة، صف القائمة، الشارة. */
const APP_LIST: Pair[] = [
  BODY,
  ["الشريط الجانبي", "aside", ".side", ["background-color", "padding-top", "padding-left", "border-right-color>border-left-color", "border-right-width>border-left-width", "row-gap"]],
  ["شعار الشريط", "aside .lock", ".side .brand", ["height", "margin-bottom"]],
  ["بند التنقل النشط", "aside > div:nth-of-type(2)", ".side nav.main .router-link-active", ["background-color", "color", "font-weight", "border-top-left-radius", "padding-top", "padding-left", "column-gap"]],
  ["بند التنقل", "aside > div:nth-of-type(3)", ".side nav.main .nav-item:not(.router-link-active)", ["color", "font-weight", "padding-top", "padding-left"]],
  ["أيقونة التنقل", "aside .ic", ".side nav.main .ic", ["width", "height"]],
  ["صورة المستخدم", "aside span[style*='50%']", ".side .avatar", ["width", "height", "background-color"]],
  ["المحتوى", "main", "main.wrap", ["padding-top", "padding-left", "padding-right", "row-gap"]],
  ["عنوان الصفحة", "main h2", ".page-head h1", TEXT],
  ["الزر الأساسي", ".btn.pri", ".page-head .btn.primary", ["background-color", "color", "border-top-left-radius", "font-family", "font-size", "font-weight", "padding-left", "padding-top"]],
  ["صف القائمة", "main .card[style*='14px 18px']", ".list-row", [...SURFACE, "padding-top", "padding-left", "column-gap"]],
  ["عنوان الصف", "main .card[style*='14px 18px'] b", ".list-row strong", ["color", "font-weight", "font-size"]],
  ["سطر الصف الباهت", "main .card[style*='14px 18px'] .muted", ".list-row .who .muted", ["color", "font-size"]],
  ["الشارة", ".chip", ".list-row .pill:not(.is-delivered)", ["background-color", "color", "font-size", "border-top-left-radius", "padding-left", "padding-top"]],
];

/** الحالة الفارغة والتنبيه والحقول، كلٌّ من الصفحة التي تعرضه. */
const APP_EMPTY: Pair[] = [
  ["بطاقة الحالة الفارغة", ".card.motif", ".empty", ["background-color", "border-top-color", "border-top-width", "border-top-left-radius"]],
  ["لوح الحالة الفارغة", ".card.motif > div", ".empty .inner", [...SURFACE, "padding-top", "padding-left", "max-width"]],
  ["رمز الحالة الفارغة", ".card.motif > div > div", ".empty .mark", ["width"]],
  ["نص الحالة الفارغة", ".card.motif p", ".empty p", ["color", "font-size"]],
];
const APP_ALERT: Pair[] = [
  ["التنبيه", "[role=alert]", ".notice", ["background-color", "color", "border-top-left-radius", "padding-top", "padding-left", "border-right-width", "border-right-color"]],
];
const APP_FORM: Pair[] = [
  ["الحقل", ".input", ".field input", ["height", "background-color", "border-top-color", "border-top-width", "border-top-left-radius", "padding-left"]],
  ["تسمية الحقل", ".field span", ".field > span", ["color", "font-size"]],
];

for (const [screen, colorScheme] of [["app-light", "light"], ["app-dark", "dark"]] as const) {
  test(`${screen}: هيكل التطبيق وعناصره`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: viewportOf(screen), colorScheme });
    const guide = await context.newPage();
    await openGuide(guide, screen);

    const list = await context.newPage();
    await openApp(list, "/orders");
    await compare(guide, list, APP_LIST, KNOWN[screen]);
    expect(await tracks(list, ".shell")).toEqual(await tracks(guide, "body > div"));

    const empty = await context.newPage();
    await openApp(empty, "/orders", { orders: [] });
    await compare(guide, empty, APP_EMPTY);

    const alert = await context.newPage();
    await openApp(alert, "/orders", { offline: true });
    await compare(guide, alert, APP_ALERT);

    const form = await context.newPage();
    await openApp(form, "/orders/new");
    await compare(guide, form, APP_FORM);
    await context.close();
  });
}

test("mobile: الشعار والبطاقة الافتتاحية وشريط التبويبات", async ({ browser }) => {
  const context = await browser.newContext({ viewport: viewportOf("mobile"), colorScheme: "light" });
  const guide = await context.newPage();
  await openGuide(guide, "mobile");

  const visitor = await context.newPage();
  await openApp(visitor, "/", { staff: false });
  await compare(guide, visitor, [
    BODY,
    ["الشعار", ".lock", ".side .brand", ["height"]],
    ["البطاقة الافتتاحية", "body > div > div:nth-child(3)", ".pitch", ["background-color", "color", "border-top-left-radius", "padding-top", "padding-left"]],
    ["عنوان البطاقة", "h2", ".pitch h1", TEXT],
    ["زر البطاقة", "body > div > div:nth-child(3) .btn", ".pitch .btn.primary", ["background-color", "color", "border-top-left-radius", "font-size", "font-weight"]],
  ]);

  const staff = await context.newPage();
  await openApp(staff, "/orders");
  await compare(guide, staff, [
    ["شريط التبويبات", "nav", ".side nav.main", ["background-color", "border-top-color", "border-top-width"]],
    ["التبويب النشط", "nav > span:nth-child(1)", ".side nav.main .router-link-active", ["color", "font-size", "row-gap"]],
    ["التبويب", "nav > span:nth-child(2)", ".side nav.main .nav-item:not(.router-link-active)", ["color", "font-size"]],
    ["أيقونة التبويب", "nav .ic", ".side nav.main .ic", ["width", "height"]],
    ["البطاقة", ".card", ".list-row", [...SURFACE, "padding-top"]],
    ["عنوان البطاقة", ".card b", ".list-row strong", ["color", "font-weight", "font-size"]],
    ["سطر البطاقة الباهت", ".card .muted", ".list-row .who .muted", ["color", "font-size"]],
  ]);
  // الشريط ملتصق بأسفل الشاشة كما في الدليل.
  const bar = await staff.locator(".side nav.main").boundingBox();
  expect(Math.round((bar?.y ?? 0) + (bar?.height ?? 0))).toBe(viewportOf("mobile").height);
  await context.close();
});

test("landing: صفحة الزائر", async ({ browser }) => {
  const context = await browser.newContext({ viewport: viewportOf("landing"), colorScheme: "light" });
  const guide = await context.newPage();
  await openGuide(guide, "landing");
  const visitor = await context.newPage();
  await openApp(visitor, "/", { staff: false });
  await compare(guide, visitor, [
    BODY,
    ["الشعار اللفظي", ".chip", ".slogan", ["background-color", "color", "font-size", "border-top-left-radius", "padding-left", "padding-top"]],
    ["العنوان", "h1", ".pitch h1", TEXT],
    ["الزر الأساسي", ".btn.pri", ".cta .btn.primary", ["background-color", "color", "border-top-left-radius", "font-size", "font-weight", "padding-left", "height"]],
    ["الزر الثانوي", "main .btn.sec", ".cta .btn:not(.primary)", ["background-color", "color", "border-top-color", "border-top-width", "border-top-left-radius"]],
    ["بطاقة الشخصية", "main .card", ".traits .panel", [...SURFACE, "padding-top", "padding-left"]],
    ["عنوان بطاقة الشخصية", "main .card b.h", ".traits h2", TEXT],
    ["نص بطاقة الشخصية", "main .card p", ".traits p", ["color", "font-size"]],
    ["لوحة النمط", "aside.motif", ".brand-panel", ["background-color"]],
    ["لوح الرمز", "aside.motif > div", ".brand-panel .card", [...SURFACE, "width", "height"]],
  ]);
  await context.close();
});

test("print: الورقة المطبوعة", async ({ browser }) => {
  const context = await browser.newContext({ viewport: viewportOf("print"), colorScheme: "dark" });
  const guide = await context.newPage();
  await openGuide(guide, "print");
  const sheet = await context.newPage();
  await sheet.emulateMedia({ media: "print", colorScheme: "dark" });
  await openApp(sheet, "/orders");
  await compare(guide, sheet, [
    ["حبر الورقة", "body", "body", ["color", "font-family"]],
    ["رأس الورقة", "body > div > div:first-child", ".print-head", ["display", "border-bottom-color", "border-bottom-width", "padding-bottom"]],
    ["شعار الرأس", ".lock", ".print-head svg", ["height"]],
    ["تذييل الورقة", "body > div > div:last-child", ".print-foot", ["display", "font-size", "border-top-color", "border-top-width", "padding-top", "color"]],
    ["عنوان الورقة", "h2", ".page-head h1", ["color", "font-family", "font-weight"]],
  ]);
  // ما لا يُطبع: الشريط الجانبي والأزرار.
  await expect(sheet.locator(".side")).toBeHidden();
  await expect(sheet.locator(".page-head .btn")).toBeHidden();
  await context.close();
});
