// نداءات الشبكة للجلسة. كلمة المرور تمرّ إلى الخادم ولا تُحفظ في أي مخزن.
import { api, ApiError } from "@/api/client";

export interface SessionUser {
  id: number;
  username: string;
  is_staff: boolean;
}

export const sessionService = {
  /** null حين لا جلسة (401)؛ أي خطأ آخر يُرمى. */
  async me(): Promise<SessionUser | null> {
    try {
      return await api.get<SessionUser>("/api/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  login: (username: string, password: string) =>
    api.post<SessionUser>("/api/auth/login", { username, password }),
  logout: () => api.post<{ ok: boolean }>("/api/auth/logout", {}),
};
