import type { Router } from "vue-router";
import { useSessionStore } from "@/stores/session";

/** الصفحات ذات `meta.requiresStaff` لا تُفتح بلا جلسة مشرف. الحماية الفعلية في الخادم؛ هذا توجيه فقط. */
export function installGuards(router: Router): void {
  router.beforeEach(async (to) => {
    if (!to.meta.requiresStaff) return true;
    const session = useSessionStore();
    await session.ensureChecked();
    return session.isStaff ? true : { name: "login", query: { next: to.fullPath } };
  });
}
