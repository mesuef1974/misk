import { createRouter, createWebHistory } from "vue-router";

// Lazy loading لكل صفحة (قاعدة الواجهة).
export const router = createRouter({
  history: createWebHistory("/"),
  routes: [
    { path: "/", name: "home", component: () => import("@/pages/HomePage.vue") },
    { path: "/about", name: "about", component: () => import("@/pages/AboutPage.vue") },
  ],
});
