import { contrast, resolveColor, rootDeclarations, type Mode } from "./tokenSource";

// القيم المعتمدة في الهوية v8 (brand/misk/identity/ADOPTION.yaml: token_map)، نهارًا وليلًا.
const IDENTITY: Record<string, [string, string]> = {
  "--bg": ["#f8f2e9", "#1f1518"],
  "--surface": ["#fdf2f5", "#312529"],
  "--ink": ["#35242c", "#fdf2f5"],
  "--muted": ["#6c5c61", "#c4b6ba"],
  "--line": ["#ddd0d4", "#5d4e53"],
  "--accent": ["#68112f", "#e4a8b3"],
  "--risk": ["#76021a", "#ff9a99"],
};
const GROUNDS = ["--bg", "--surface", "--raised", "--brand-soft"];
const MODES: Mode[] = ["day", "night"];

describe("ألوان المنصة في الوضعين", () => {
  it("كل متغير من token_map يحمل قيمة الهوية نهارًا وقيمتها ليلًا", () => {
    const declarations = rootDeclarations();
    for (const [name, [day, night]] of Object.entries(IDENTITY)) {
      // قيمة واحدة بلا light-dark تُبقي الصفحة نهارية في الوضع الليلي.
      expect(declarations.get(name), name).toMatch(/^light-dark\(/);
      expect(resolveColor(name, "day"), `${name} نهارًا`).toBe(day);
      expect(resolveColor(name, "night"), `${name} ليلًا`).toBe(night);
    }
  });

  it.each(MODES)("النص والتمييز يبلغان حدّ التباين على كل سطح (%s)", (mode) => {
    for (const ground of GROUNDS.map((name) => resolveColor(name, mode))) {
      expect(contrast(resolveColor("--ink", mode), ground)).toBeGreaterThanOrEqual(7);
      expect(contrast(resolveColor("--muted", mode), ground)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(resolveColor("--accent", mode), ground)).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(resolveColor("--on-accent", mode), resolveColor("--accent", mode))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(resolveColor("--risk", mode), resolveColor("--bg", mode))).toBeGreaterThanOrEqual(4.5);
  });

  it("الرمز بلون السمة نهارًا وأبيض ليلًا، ظاهر على الخلفية والسطح", () => {
    expect(resolveColor("--color-mark-ink", "day")).toBe("#68112f");
    expect(resolveColor("--color-mark-ink", "night")).toBe("#ffffff");
    for (const mode of MODES) {
      for (const ground of ["--bg", "--surface"]) {
        expect(contrast(resolveColor("--color-mark-ink", mode), resolveColor(ground, mode))).toBeGreaterThanOrEqual(3);
      }
    }
  });
});
