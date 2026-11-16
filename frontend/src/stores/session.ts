import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiError } from "@/api/client";
import { sessionService, type SessionUser } from "@/services/session";

export const useSessionStore = defineStore("session", () => {
  const user = ref<SessionUser | null>(null);
  const checked = ref(false);
  let pending: Promise<void> | null = null;

  const isStaff = computed(() => user.value?.is_staff === true);

  /** يسأل الخادم مرة واحدة عمّن يملك الجلسة؛ النداءات المتزامنة تشترك في الطلب نفسه. */
  function ensureChecked(): Promise<void> {
    if (checked.value) return Promise.resolve();
    pending ??= sessionService
      .me()
      .then((me) => {
        user.value = me;
        checked.value = true;
      })
      .catch(() => {
        // تعذّر السؤال (شبكة أو خادم): نعامله كغياب الجلسة ونعيد السؤال في التنقل التالي.
        user.value = null;
      })
      .finally(() => {
        pending = null;
      });
    return pending;
  }

  async function login(username: string, password: string): Promise<void> {
    user.value = await sessionService.login(username, password);
    checked.value = true;
  }

  async function logout(): Promise<void> {
    try {
      await sessionService.logout();
    } catch (error) {
      // 401: الجلسة انتهت أصلًا، والنتيجة المطلوبة تحققت.
      if (!(error instanceof ApiError && error.status === 401)) throw error;
    }
    user.value = null;
    checked.value = true;
  }

  return { user, checked, isStaff, ensureChecked, login, logout };
});
