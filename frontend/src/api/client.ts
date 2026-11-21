// عميل fetch صغير: جلسة Django (كوكي HttpOnly) + CSRF من كوكي csrftoken. لا توكنات في localStorage.

import { i18n } from "@/i18n";

/** خطأ من الخادم أو من الشبكة. `status` صفر حين لا يصل الطلب أصلًا. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// رسائل الواجهة نفسها بلغة الصفحة؛ `detail` الآتي من الخادم يُنقل كما هو.
const FALLBACK_KEYS = {
  0: "errors.network",
  401: "errors.unauthorized",
  403: "errors.forbidden",
  404: "errors.notFound",
  429: "errors.tooMany",
} as const;

function fallback(status: number): string {
  const key = (FALLBACK_KEYS as Record<number, (typeof FALLBACK_KEYS)[keyof typeof FALLBACK_KEYS] | undefined>)[status];
  return key ? i18n.global.t(key) : i18n.global.t("errors.failed", { status });
}

/** مسارات الجلسة نفسها: 401 فيها جواب متوقَّع (لا جلسة، كلمة مرور خاطئة) لا جلسة انتهت أثناء العمل. */
const SESSION_URLS = ["/api/me", "/api/auth/"];

let onUnauthorized: (() => void) | null = null;

/** يُستدعى حين يرد الخادم 401 على طلب عمل: الجلسة انتهت. يسجّله الموجِّه ليعيد إلى صفحة الدخول. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** الكوكي أولًا: Django يبدّل الرمز عند تسجيل الدخول، فقيمة <meta> التي حُمّلت مع الصفحة تبطل بعده. */
function csrfToken(): string {
  const cookie = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="));
  if (cookie) return decodeURIComponent(cookie.slice("csrftoken=".length));
  return document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";
}

interface ValidationIssue {
  loc?: unknown[];
  msg?: string;
}

/** Ninja يعيد `detail` نصًّا لأخطاء العمل، وقائمة لأخطاء التحقق من المخطط. */
async function serverDetail(res: Response): Promise<string> {
  try {
    const detail = ((await res.json()) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return (detail as ValidationIssue[])
        .map((issue) => [(issue.loc ?? []).slice(1).join("."), issue.msg ?? ""].filter(Boolean).join(": "))
        .join("؛ ");
    }
  } catch {
    // جسم غير JSON: تكفي رسالة الحالة.
  }
  return "";
}

async function request<T>(
  method: string,
  url: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-CSRFToken": csrfToken() } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, fallback(0));
  }
  if (!res.ok) {
    if (res.status === 401 && !SESSION_URLS.some((prefix) => url.startsWith(prefix))) onUnauthorized?.();
    // 401 من Ninja نصّه «Unauthorized»؛ رسالتنا العربية أوضح. رسالة رفض تسجيل الدخول عربية فتُنقل.
    const raw = await serverDetail(res);
    const detail = raw === "Unauthorized" ? "" : raw;
    throw new ApiError(res.status, detail || fallback(res.status));
  }
  return (await res.json()) as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : i18n.global.t("errors.unexpected");
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  /** `headers` لترويسات العملية نفسها، مثل X-Request-ID لمنع التسجيل المكرر. */
  post: <T>(url: string, body: unknown, headers?: Record<string, string>) =>
    request<T>("POST", url, body, headers),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
};
