import { defineStore } from "pinia";
import { api } from "@/api/client";
import { DEFAULT_LOCALE, type Locale } from "@/domain/locale";

// الاسم العربي من الخادم (SITE_TITLE، المصدر نفسه للوحة الإدارة)؛ هذا رسمه اللاتيني للواجهة الإنجليزية.
const SITE_TITLE_LATIN = "Misk";

interface PingOut {
  ok: boolean;
  site: string;
}

export const useAppStore = defineStore("app", {
  state: () => ({
    siteTitle: document.getElementById("app")?.dataset.siteTitle ?? "",
    backendOk: null as boolean | null,
  }),
  getters: {
    title: (state) => (locale: Locale) => (locale === DEFAULT_LOCALE ? state.siteTitle : SITE_TITLE_LATIN),
  },
  actions: {
    async loadPing() {
      try {
        const data = await api.get<PingOut>("/api/ping");
        this.backendOk = data.ok;
        if (data.site) this.siteTitle = data.site;
      } catch {
        this.backendOk = false;
      }
    },
  },
});
