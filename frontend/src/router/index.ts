import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

// Lazy loading لكل صفحة (قاعدة الواجهة).
export const routes: RouteRecordRaw[] = [
  { path: "/", name: "home", component: () => import("@/pages/HomePage.vue") },
  { path: "/about", name: "about", component: () => import("@/pages/AboutPage.vue") },
  { path: "/orders", name: "orders", component: () => import("@/pages/OrdersPage.vue") },
  { path: "/orders/new", name: "order-new", component: () => import("@/pages/OrderNewPage.vue") },
  {
    path: "/orders/:id(\\d+)",
    name: "order-detail",
    component: () => import("@/pages/OrderDetailPage.vue"),
    props: (route) => ({ orderId: Number(route.params.id) }),
  },
];

export const router = createRouter({ history: createWebHistory("/"), routes });
