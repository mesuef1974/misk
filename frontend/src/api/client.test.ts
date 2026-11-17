import { api, ApiError, errorMessage } from "./client";

function respond(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(typeof body === "string" ? body : JSON.stringify(body), { status })),
  );
}

async function failure(call: Promise<unknown>): Promise<ApiError> {
  const error = await call.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("عميل API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.head.innerHTML = "";
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("يفضّل رمز CSRF من الكوكي على <meta> القديم", async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="stale">';
    document.cookie = "csrftoken=fresh";
    respond(200, { ok: true });
    await api.post("/api/x", {});
    const headers = vi.mocked(fetch).mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["X-CSRFToken"]).toBe("fresh");
  });

  it("يرسل CSRF مع الكتابة لا مع القراءة", async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="tok">';
    respond(200, { ok: true });
    await api.get("/api/x");
    await api.post("/api/x", { a: 1 });
    const calls = vi.mocked(fetch).mock.calls.map(([, init]) => (init?.headers ?? {}) as Record<string, string>);
    expect(calls[0]["X-CSRFToken"]).toBeUndefined();
    expect(calls[1]["X-CSRFToken"]).toBe("tok");
    expect(calls[1]["Content-Type"]).toBe("application/json");
  });

  it("ينقل رسالة الخادم النصية", async () => {
    respond(409, { detail: "لا انتقال من «مُسلَّم» إلى «مسودة»" });
    const error = await failure(api.post("/api/x", {}));
    expect(error.status).toBe(409);
    expect(error.message).toBe("لا انتقال من «مُسلَّم» إلى «مسودة»");
  });

  it("يجمع أخطاء التحقق من المخطط", async () => {
    respond(422, { detail: [{ loc: ["body", "payload", "customer_name"], msg: "Field required" }] });
    expect((await failure(api.post("/api/x", {}))).message).toBe("payload.customer_name: Field required");
  });

  it("يعرّب 401 ولا يعرض نص الخادم", async () => {
    respond(401, { detail: "Unauthorized" });
    expect((await failure(api.get("/api/x"))).message).toBe("يلزم تسجيل الدخول بحساب مشرف");
  });

  it("ينقل رسالة رفض تسجيل الدخول ويعرّب القفل", async () => {
    respond(401, { detail: "اسم المستخدم أو كلمة المرور غير صحيحة" });
    expect((await failure(api.post("/api/auth/login", {}))).message).toBe("اسم المستخدم أو كلمة المرور غير صحيحة");
    respond(429, "Account locked");
    expect((await failure(api.post("/api/auth/login", {}))).message).toBe("محاولات كثيرة؛ حاول بعد قليل");
  });

  it("يتحمّل جسمًا غير JSON وانقطاع الشبكة", async () => {
    respond(500, "<html>");
    expect((await failure(api.get("/api/x"))).message).toBe("تعذّر إتمام العملية (500)");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const offline = await failure(api.get("/api/x"));
    expect(offline.status).toBe(0);
    expect(errorMessage(offline)).toBe("تعذّر الاتصال. تحقّق من الشبكة ثم أعد المحاولة");
    expect(errorMessage(new Error("x"))).toBe("حدث خطأ غير متوقع");
  });
});
