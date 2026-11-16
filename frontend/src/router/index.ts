import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { installGuards } from "./guards";

declare module "vue-router" {
  interface RouteMeta {
    requiresStaff?: boolean;
  }
}

const staffOnly = { requiresStaff: true };

// Lazy loading لكل صفحة (قاعدة الواجهة).
export const routes: RouteRecordRaw[] = [
  { path: "/", name: "home", component: () => import("@/pages/HomePage.vue") },
  { path: "/about", name: "about", component: () => import("@/pages/AboutPage.vue") },
  { path: "/login", name: "login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/orders", name: "orders", meta: staffOnly, component: () => import("@/pages/OrdersPage.vue") },
  { path: "/orders/new", name: "order-new", meta: staffOnly, component: () => import("@/pages/OrderNewPage.vue") },
  {
    path: "/orders/:id(\\d+)",
    name: "order-detail",
    meta: staffOnly,
    component: () => import("@/pages/OrderDetailPage.vue"),
    props: (route) => ({ orderId: Number(route.params.id) }),
  },
  { path: "/production", name: "production", meta: staffOnly, component: () => import("@/pages/ProductionPage.vue") },
  { path: "/materials", name: "materials", meta: staffOnly, component: () => import("@/pages/MaterialsPage.vue") },
  { path: "/templates", name: "templates", meta: staffOnly, component: () => import("@/pages/TemplatesPage.vue") },
];

export const router = createRouter({ history: createWebHistory("/"), routes });
installGuards(router);
