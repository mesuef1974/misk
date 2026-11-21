// وجهة ما بعد تسجيل الدخول تأتي من عنوان الصفحة، فلا تُقبل إلا مسارًا داخل الموقع (لا إعادة توجيه مفتوحة).

import { stripLocale } from "@/domain/locale";

export const DEFAULT_AFTER_LOGIN = "/";

export function safeNext(next: unknown): string {
  if (typeof next !== "string") return DEFAULT_AFTER_LOGIN;
  // «//host» والشرطة المعكوسة يفسّرهما المتصفح عنوانًا خارجيًّا.
  if (!next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return DEFAULT_AFTER_LOGIN;
  const bare = stripLocale(next);
  if (bare === "/login" || bare.startsWith("/login?")) return DEFAULT_AFTER_LOGIN;
  return next;
}
