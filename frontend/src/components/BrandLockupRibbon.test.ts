import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { PALETTES } from "@/domain/theme";
import { useThemeStore } from "@/stores/theme";
import BrandLockupRibbon from "./BrandLockupRibbon.vue";

describe("BrandLockupRibbon", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("لكل سمة من العشر نسخة PNG تُعرض باسمها", async () => {
    const theme = useThemeStore();
    const lockup = mount(BrandLockupRibbon, { props: { height: 88 } });
    for (const { id } of PALETTES) {
      theme.setPalette(id);
      await lockup.vm.$nextTick();
      expect(lockup.find("img.ribbon").attributes("src")).toContain(`misk-lockup-ribbon-${id}.png`);
    }
  });

  it("الصورة زخرفية والقفل المسطّح احتياط الوضع الداكن", () => {
    const lockup = mount(BrandLockupRibbon, { props: { height: 88 } });
    expect(lockup.find("img.ribbon").attributes("alt")).toBe("");
    expect(lockup.find("svg.brand-lockup").attributes("aria-hidden")).toBe("true");
    expect(lockup.text()).toBe("");
  });
});
