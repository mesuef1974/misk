import { mount } from "@vue/test-utils";
import StatusCard from "./StatusCard.vue";

describe("StatusCard", () => {
  it("يعرض حالة الانتظار", () => {
    const w = mount(StatusCard, { props: { ok: null } });
    expect(w.text()).toContain("يتحقق");
  });
  it("يعرض نجاح الخادم", () => {
    const w = mount(StatusCard, { props: { ok: true } });
    expect(w.text()).toContain("يعمل");
    expect(w.classes()).toContain("ok");
  });
});
