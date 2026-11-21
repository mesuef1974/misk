import { configDefaults, defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// يبني إلى ../frontend_dist حيث يقرأه django-vite عبر .vite/manifest.json، وWhiteNoise يخدمه.
export default defineConfig({
  plugins: [vue()],
  base: "/static/",
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    origin: "http://127.0.0.1:5173",
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    manifest: true,
    outDir: "../frontend_dist",
    emptyOutDir: true,
    rollupOptions: { input: "src/main.ts" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // vue-i18n لكل مكوّن يُركَّب في الاختبار، والعودة إلى العربية قبل كل اختبار.
    setupFiles: ["src/test-setup.ts"],
    // e2e/ اختبارات Playwright (npm run test:screens)، لا يشغّلها vitest.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
