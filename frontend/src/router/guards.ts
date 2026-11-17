import type { Router } from "vue-router";
import { setUnauthorizedHandler } from "@/api/client";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { useSessionStore } from "@/stores/session";

/** الصفحات ذات `meta.requiresStaff` لا تُفتح بلا جلسة مشرف. الحماية الفعلية في الخادم؛ هذا توجيه فقط. */
export function installGuards(router: Router): void {
  router.beforeEach(async (to) => {
    if (!to.meta.requiresStaff) return true;
    const session = useSessionStore();
    await session.ensureChecked();
    if (session.isStaff) return true;
    // تعذّر سؤال الخادم (شبكة أو عطل): لا نحكم بغياب الجلسة ولا نرسل مشرفًا داخلًا إلى صفحة الدخول.
    // الصفحة تعرض خطأ التحميل وزر إعادة المحاولة، وإن كانت الجلسة غائبة فعلًا فأول 401 يعيد إلى الدخول.
    if (!session.checked) return true;
    return { name: "login", query: { next: to.fullPath } };
  });

  // 401 أثناء العمل: الجلسة انتهت في الخادم. بيانات المشرف لا تبقى في الذاكرة، والعودة بعد الدخول إلى الصفحة نفسها.
  setUnauthorizedHandler(() => {
    useSessionStore().expire();
    useOrdersStore().clear();
    useProductionStore().clear();
    useCatalogStore().clear();
    const current = router.currentRoute.value;
    if (current.meta.requiresStaff) void router.push({ name: "login", query: { next: current.fullPath } });
  });
}
