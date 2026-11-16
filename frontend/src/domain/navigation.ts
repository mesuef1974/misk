// وجهة ما بعد تسجيل الدخول تأتي من عنوان الصفحة، فلا تُقبل إلا مسارًا داخل الموقع (لا إعادة توجيه مفتوحة).

export const DEFAULT_AFTER_LOGIN = "/orders";

export function safeNext(next: unknown): string {
  if (typeof next !== "string") return DEFAULT_AFTER_LOGIN;
  // «//host» والشرطة المعكوسة يفسّرهما المتصفح عنوانًا خارجيًّا.
  if (!next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return DEFAULT_AFTER_LOGIN;
  if (next === "/login" || next.startsWith("/login?")) return DEFAULT_AFTER_LOGIN;
  return next;
}
