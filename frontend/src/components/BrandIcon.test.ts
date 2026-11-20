import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import BrandIcon from "./BrandIcon.vue";

describe("BrandIcon", () => {
  it("يحقن الأيقونة زخرفية بلا عنوان يدخل نص الصفحة", () => {
    const icon = mount(BrandIcon, { props: { name: "order" } });
    expect(icon.find("svg").exists()).toBe(true);
    expect(icon.find("title").exists()).toBe(false);
    expect(icon.text()).toBe("");
    expect(icon.find(".ic").attributes("aria-hidden")).toBe("true");
  });
});
