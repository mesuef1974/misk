// عميل fetch صغير: جلسة Django (كوكي HttpOnly) + CSRF من <meta>. لا توكنات في localStorage.

/** خطأ من الخادم أو من الشبكة. `status` صفر حين لا يصل الطلب أصلًا. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const FALLBACK: Record<number, string> = {
  0: "تعذّر الاتصال بالخادم",
  401: "يلزم تسجيل الدخول بحساب مشرف",
  403: "لا صلاحية لهذا الإجراء",
  404: "غير موجود",
};

function csrfToken(): string {
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

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-CSRFToken": csrfToken() } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, FALLBACK[0]);
  }
  if (!res.ok) {
    // 401 من Ninja نصّه «Unauthorized»؛ رسالتنا العربية أوضح للمستخدم.
    const detail = res.status === 401 ? "" : await serverDetail(res);
    throw new ApiError(res.status, detail || FALLBACK[res.status] || `تعذّر تنفيذ الطلب (${res.status})`);
  }
  return (await res.json()) as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "حدث خطأ غير متوقع";
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body: unknown) => request<T>("POST", url, body),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  del: <T>(url: string) => request<T>("DELETE", url),
};
