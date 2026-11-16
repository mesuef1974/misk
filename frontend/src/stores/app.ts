import { defineStore } from "pinia";
import { api } from "@/api/client";

interface PingOut {
  ok: boolean;
  site: string;
}

export const useAppStore = defineStore("app", {
  state: () => ({
    siteTitle: document.getElementById("app")?.dataset.siteTitle ?? "",
    backendOk: null as boolean | null,
  }),
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
