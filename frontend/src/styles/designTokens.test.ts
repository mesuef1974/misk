import { CSS_SOURCES, rootDeclarations, TOKENS_CSS } from "./tokenSource";

// خيارات glob حرفية في كل نداء: Vite يحلّلها قبل التشغيل.
const styles = CSS_SOURCES;
const components = import.meta.glob<string>("../**/*.vue", { query: "?raw", import: "default", eager: true });
const icons = import.meta.glob<string>("../../public/favicon.svg", { query: "?raw", import: "default", eager: true });

const sources = { ...styles, ...components };
const mark = components["../components/BrandMark.vue"];
const favicon = Object.values(icons)[0];
const pathData = (text: string): string[] => [...text.matchAll(/<path\b[^>]*? d="([^"]+)"/g)].map((match) => match[1]);

describe("رموز الهوية في الواجهة", () => {
  it("كل متغير تقرؤه الأنماط والمكوّنات معرَّف", () => {
    expect(Object.keys(styles).length).toBeGreaterThan(2);
    expect(Object.keys(components).length).toBeGreaterThan(10);
    const defined = new Set<string>();
    for (const text of Object.values(sources)) {
      for (const match of text.matchAll(/(?<![\w-])(--[\w-]+)\s*:/g)) defined.add(match[1]);
    }
    const missing: string[] = [];
    for (const [file, text] of Object.entries(sources)) {
      // var(--x, بديل) يحمل بديله؛ ما بلا بديل يجب أن يُعرَّف.
      for (const match of text.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)) {
        if (!defined.has(match[1])) missing.push(`${file}: ${match[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("متغيرات الشعار: حبر واحد، ولا مربع ولا نقطة ولا طيّات", () => {
    const declarations = rootDeclarations();
    expect(declarations.get("--color-mark-ink")).toBe("light-dark(var(--day-color), #ffffff)");
    // كلمة القفل المولَّد تقرأ --color-ink.
    expect(declarations.get("--color-ink")).toBe("var(--ink)");
    for (const old of ["--color-mark-tile", "--color-mark-dot", "--color-mark-accent", "--color-mark-fold"]) {
      expect(TOKENS_CSS).not.toContain(old);
      for (const [file, text] of Object.entries(sources)) expect(text.includes(old), `${file}: ${old}`).toBe(false);
    }
  });

  it("الرمز مسار واحد بحبر العلامة، وهو نفسه أيقونة المتصفح، بلا مربع خلفه", () => {
    expect(pathData(mark)).toHaveLength(1);
    expect(pathData(favicon)).toEqual(pathData(mark));
    expect([...mark.matchAll(/fill="([^"]+)"/g)].map((match) => match[1])).toEqual(["var(--color-mark-ink, #68112F)"]);
    for (const text of [mark, favicon]) expect(text).not.toContain("<rect");
  });

  it("أيقونة المتصفح تبيضّ على شريط التبويب الداكن كحبر العلامة ليلًا", () => {
    expect(favicon).toMatch(/@media \(prefers-color-scheme: dark\) \{ path \{ fill: #ffffff; \} \}/);
  });

  it("لا يبقى شعار الهوية السابقة في مكوّن ولا قناع", () => {
    const names = Object.keys(components).filter((file) => /\/Brand\w+\.vue$/.test(file)).sort();
    expect(names).toEqual(["BrandIcon", "BrandLockup", "BrandMark", "BrandPanel"].map((name) => `../components/${name}.vue`));
    const viewBox = /viewBox="0 0 100 ([\d.]+)"/.exec(mark)?.[1];
    expect(viewBox).toBeDefined();
    expect(styles["./base.css"]).toContain(`aspect-ratio: 100 / ${viewBox};`);
    expect(styles["../static/brand/splash.css"]).toContain(`aspect-ratio: 100 / ${viewBox};`);
    for (const [file, text] of Object.entries(sources)) expect(text.includes("65.85071"), file).toBe(false);
  });
});
