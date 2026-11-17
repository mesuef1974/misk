import { defineConfig } from "@playwright/test";

// اختبار مقارنة الصفحات بشاشات دليل الهوية (e2e/screens.spec.ts). يُشغَّل محليًّا: npm run test:screens
// المتصفح: Chromium المنزَّل بـ `npx playwright install chromium`، أو متصفح النظام بـ PLAYWRIGHT_CHANNEL=msedge.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173/static/src/main.ts",
    reuseExistingServer: true,
  },
});
