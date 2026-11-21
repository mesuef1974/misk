import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { PALETTES } from "@/domain/theme";
import { setLocale } from "@/i18n";
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
      expect(lockup.get("img").attributes("src")).toContain(`misk-lockup-ribbon-${id}.png`);
    }
  });

  it("في الإنجليزية لكل سمة نسخة «Misk» بالاسم -en-، وتعود العربية بعودة اللغة", async () => {
    const theme = useThemeStore();
    const lockup = mount(BrandLockupRibbon, { props: { height: 88 } });
    await setLocale("en");
    for (const { id } of PALETTES) {
      theme.setPalette(id);
      await lockup.vm.$nextTick();
      expect(lockup.get("img").attributes("src")).toContain(`misk-lockup-ribbon-en-${id}.png`);
    }
    await setLocale("ar");
    await lockup.vm.$nextTick();
    expect(lockup.get("img").attributes("src")).not.toContain("-en-");
  });

  it("الصورة زخرفية بلا نص بديل يكرّر الاسم", () => {
    const lockup = mount(BrandLockupRibbon, { props: { height: 88 } });
    expect(lockup.get("img").attributes("alt")).toBe("");
    expect(lockup.text()).toBe("");
  });
});
