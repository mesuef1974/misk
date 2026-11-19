// قراءة ألوان المنصة من static/brand/tokens.css نصًّا، لاختبارَي designTokens وcontrast: jsdom لا يحسب light-dark ولا var.
// تُقرأ ملفات CSS من القرص: vitest يستبدل CSS المستورد (ولو بـ ?raw) بنص فارغ.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

// جذر vitest مجلد frontend (import.meta.url في jsdom ليس مسار ملف).
const SRC = join(process.cwd(), "src");

/** كل ملفات CSS تحت src، مفتاحها مسارها نسبةً إلى styles/ كما في import.meta.glob ("./base.css"، "../static/brand/tokens.css"). */
export const CSS_SOURCES: Record<string, string> = Object.fromEntries(
  readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .map((path) => path.replaceAll("\\", "/"))
    .filter((path) => path.endsWith(".css"))
    .map((path) => [path.startsWith("styles/") ? `./${path.slice(7)}` : `../${path}`, readFileSync(join(SRC, path), "utf8")]),
);

export const TOKENS_CSS: string = CSS_SOURCES["../static/brand/tokens.css"] ?? "";

export type Mode = "day" | "night";

const stripComments = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, "");

/** تعريفات الصفحة بلا سمة مختارة (العودي افتراضي): كل ما في tokens.css عدا قواعد [data-palette]. */
export function rootDeclarations(css: string = TOKENS_CSS): Map<string, string> {
  const root = stripComments(css).replace(/\[data-palette[^{]*\{[^}]*\}/g, "");
  return new Map([...root.matchAll(/(--[\w-]+)\s*:\s*([^;{}]+);/g)].map((match) => [match[1], match[2].trim()]));
}

/** معاملا light-dark(a, b): الفاصلة التي خارج كل قوس. */
function lightDarkSides(value: string): [string, string] | null {
  if (!value.startsWith("light-dark(") || !value.endsWith(")")) return null;
  const inner = value.slice("light-dark(".length, -1);
  let depth = 0;
  for (let i = 0; i < inner.length; i += 1) {
    if (inner[i] === "(") depth += 1;
    else if (inner[i] === ")") depth -= 1;
    else if (inner[i] === "," && depth === 0) return [inner.slice(0, i).trim(), inner.slice(i + 1).trim()];
  }
  return null;
}

/** قيمة المتغير لونًا خامًا (#rrggbb بحروف صغيرة) في الوضع المطلوب؛ يرمي إن لم يُعرَّف أو لم يكن لونًا خامًا. */
export function resolveColor(name: string, mode: Mode, declarations: Map<string, string> = rootDeclarations()): string {
  let value = declarations.get(name);
  for (let hops = 0; value !== undefined && hops < 12; hops += 1) {
    if (/^#[0-9a-f]{6}$/i.test(value)) return value.toLowerCase();
    const sides = lightDarkSides(value);
    const reference = /^var\(\s*(--[\w-]+)\s*\)$/.exec(value);
    if (sides) value = sides[mode === "day" ? 0 : 1];
    else if (reference) value = declarations.get(reference[1]);
    else break;
  }
  throw new Error(`${name} (${mode}): ${value ?? "غير معرّف"}`);
}

function luminance(color: string): number {
  const channel = (offset: number): number => {
    const c = parseInt(color.slice(offset, offset + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** نسبة التباين WCAG بين لونين خامين. */
export function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}
