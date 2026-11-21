import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { installLocale } from "@/i18n/router";
import { installGuards } from "./guards";

declare module "vue-router" {
  interface RouteMeta {
    requiresStaff?: boolean;
    /** للصفحة نسخة عربية ونسخة تحت `/en` (كل الصفحات عدا «غير موجودة»). */
    localized?: boolean;
  }
}

const staffOnly = { requiresStaff: true };

// Lazy loading لكل صفحة (قاعدة الواجهة).
export const routes: RouteRecordRaw[] = [
  // كل صفحة تُعرَّف مرة واحدة وتُفتح بلغتين: `/orders` و`/en/orders`. المعامل الاختياري على الأب، فالتنقّل
  // بالاسم بين الصفحات يحمله معه ويبقى المستخدم في لغته.
  {
    path: "/:locale(en)?",
    meta: { localized: true },
    children: [
      { path: "", name: "home", component: () => import("@/pages/HomePage.vue") },
      { path: "about", name: "about", component: () => import("@/pages/AboutPage.vue") },
      { path: "login", name: "login", component: () => import("@/pages/LoginPage.vue") },
      { path: "orders", name: "orders", meta: staffOnly, component: () => import("@/pages/OrdersPage.vue") },
      { path: "orders/new", name: "order-new", meta: staffOnly, component: () => import("@/pages/OrderNewPage.vue") },
      {
        path: "orders/:id(\\d+)",
        name: "order-detail",
        meta: staffOnly,
        component: () => import("@/pages/OrderDetailPage.vue"),
        props: (route) => ({ orderId: Number(route.params.id) }),
      },
      { path: "production", name: "production", meta: staffOnly, component: () => import("@/pages/ProductionPage.vue") },
      { path: "materials", name: "materials", meta: staffOnly, component: () => import("@/pages/MaterialsPage.vue") },
      { path: "templates", name: "templates", meta: staffOnly, component: () => import("@/pages/TemplatesPage.vue") },
    ],
  },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("@/pages/NotFoundPage.vue") },
];

export const router = createRouter({ history: createWebHistory("/"), routes });
installLocale(router);
installGuards(router);
