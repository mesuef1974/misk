import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import { ApiError } from "@/api/client";
import { safeNext } from "@/domain/navigation";
import { routes } from "@/router";
import { installGuards } from "@/router/guards";
import { sessionService, type SessionUser } from "@/services/session";
import { useSessionStore } from "@/stores/session";
import LoginPage from "./LoginPage.vue";

vi.mock("@/services/session", () => ({
  sessionService: { me: vi.fn(), login: vi.fn(), logout: vi.fn() },
}));
vi.mock("@/services/orders", () => ({
  ordersService: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), transition: vi.fn() },
}));
vi.mock("@/services/catalog", () => ({
  catalogService: { materials: vi.fn().mockResolvedValue([]), templates: vi.fn().mockResolvedValue([]) },
}));

const staff: SessionUser = { id: 1, username: "staff", is_staff: true, admin_url: "/admin/" };

let router: Router;

beforeEach(() => {
  setActivePinia(createPinia());
  router = createRouter({ history: createMemoryHistory(), routes });
  installGuards(router);
  vi.mocked(sessionService.me).mockReset().mockResolvedValue(null);
  vi.mocked(sessionService.login).mockReset().mockResolvedValue(staff);
  vi.mocked(sessionService.logout).mockReset().mockResolvedValue({ ok: true });
});

describe("وجهة ما بعد الدخول", () => {
  it("تقبل المسار الداخلي وحده", () => {
    expect(safeNext("/orders/5?x=1")).toBe("/orders/5?x=1");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "orders", "/login", "/login?next=/a", undefined, ["/a"]]) {
      expect(safeNext(bad)).toBe("/orders");
    }
  });
});

describe("حارس المسارات", () => {
  it("يحوّل الزائر إلى الدخول ويحفظ وجهته", async () => {
    await router.push("/orders/5");
    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query.next).toBe("/orders/5");
  });

  it("يفتح الصفحة للمشرف ويسأل الخادم مرة واحدة", async () => {
    vi.mocked(sessionService.me).mockResolvedValue(staff);
    await router.push("/orders");
    await router.push("/orders/new");
    expect(router.currentRoute.value.name).toBe("order-new");
    expect(sessionService.me).toHaveBeenCalledTimes(1);
  });

  it("يرفض غير المشرف", async () => {
    vi.mocked(sessionService.me).mockResolvedValue({ ...staff, is_staff: false, admin_url: null });
    await router.push("/orders");
    expect(router.currentRoute.value.name).toBe("login");
  });

  it("لا يسأل الخادم للصفحات العامة، ويعيد السؤال بعد تعذّره", async () => {
    await router.push("/about");
    expect(sessionService.me).not.toHaveBeenCalled();

    vi.mocked(sessionService.me).mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"));
    await router.push("/orders");
    expect(router.currentRoute.value.name).toBe("login");
    vi.mocked(sessionService.me).mockResolvedValue(staff);
    await router.push("/orders");
    expect(router.currentRoute.value.name).toBe("orders");
  });
});

describe("صفحة الدخول", () => {
  async function open(path: string) {
    await router.push(path);
    await router.isReady();
    const page = mount(LoginPage, { global: { plugins: [router] } });
    await flushPromises();
    return page;
  }

  async function fill(page: ReturnType<typeof mount>, username: string, password: string) {
    await page.get('input[name="username"]').setValue(username);
    await page.get('input[name="password"]').setValue(password);
  }

  it("تدخل وتذهب إلى الوجهة المحفوظة", async () => {
    const page = await open("/login?next=/orders/new");
    expect(page.get('button[type="submit"]').attributes("disabled")).toBeDefined();
    await fill(page, " staff ", "correct horse");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(sessionService.login).toHaveBeenCalledWith("staff", "correct horse");
    expect(useSessionStore().user).toEqual(staff);
    expect(router.currentRoute.value.fullPath).toBe("/orders/new");
  });

  it("لا تتبع وجهة خارجية", async () => {
    const page = await open("/login?next=//evil.example");
    await fill(page, "staff", "correct horse");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe("/orders");
  });

  it("تعرض الرفض وتمسح كلمة المرور", async () => {
    vi.mocked(sessionService.login).mockRejectedValue(new ApiError(401, "اسم المستخدم أو كلمة المرور غير صحيحة"));
    const page = await open("/login");
    await fill(page, "staff", "wrong");
    await page.get("form").trigger("submit");
    await flushPromises();
    expect(page.get('[role="alert"]').text()).toBe("اسم المستخدم أو كلمة المرور غير صحيحة");
    expect((page.get('input[name="password"]').element as HTMLInputElement).value).toBe("");
    expect(useSessionStore().user).toBeNull();
    expect(router.currentRoute.value.name).toBe("login");
  });
});

describe("مخزن الجلسة", () => {
  it("الخروج ينجح ولو انتهت الجلسة، ويُبقي المستخدم عند تعذّر الخادم", async () => {
    const session = useSessionStore();
    await session.login("staff", "x");
    vi.mocked(sessionService.logout).mockRejectedValueOnce(new ApiError(0, "تعذّر الاتصال بالخادم"));
    await expect(session.logout()).rejects.toBeInstanceOf(ApiError);
    expect(session.user).toEqual(staff);

    vi.mocked(sessionService.logout).mockRejectedValueOnce(new ApiError(401, "يلزم تسجيل الدخول بحساب مشرف"));
    await session.logout();
    expect(session.user).toBeNull();
    expect(session.isStaff).toBe(false);
  });
});

describe("رابط لوحة الإدارة في القائمة", () => {
  async function nav(user: SessionUser | null) {
    vi.mocked(sessionService.me).mockResolvedValue(user);
    const { default: App } = await import("@/App.vue");
    const app = mount(App, { global: { plugins: [router] } });
    await flushPromises();
    return app.find('nav a[href="/admin/"]');
  }

  it("يظهر للمشرف بالمسار الذي يعطيه الخادم", async () => {
    const link = await nav(staff);
    expect(link.exists()).toBe(true);
    expect(link.text()).toBe("لوحة الإدارة");
  });

  it("يغيب عن الزائر وعن من لا مسار له", async () => {
    expect((await nav(null)).exists()).toBe(false);
    expect((await nav({ ...staff, is_staff: false, admin_url: null })).exists()).toBe(false);
  });
});
