<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "@/stores/app";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { THEME_LABELS } from "@/domain/theme";
import { useSessionStore } from "@/stores/session";
import { useThemeStore } from "@/stores/theme";

const store = useAppStore();
const session = useSessionStore();
const theme = useThemeStore();
const router = useRouter();
const leaving = ref(false);

onMounted(() => {
  store.loadPing();
  session.ensureChecked();
  window.addEventListener("storage", theme.onStorage);
});
onBeforeUnmount(() => window.removeEventListener("storage", theme.onStorage));

async function logout(): Promise<void> {
  leaving.value = true;
  try {
    await session.logout();
    // بيانات المشرف لا تبقى في الذاكرة بعد الخروج.
    useOrdersStore().clear();
    useProductionStore().clear();
    useCatalogStore().clear();
    await router.push({ name: "login" });
  } catch {
    // تعذّر الوصول إلى الخادم: الجلسة ما زالت قائمة والزر يبقى ظاهرًا لإعادة المحاولة.
  } finally {
    leaving.value = false;
  }
}
</script>

<template>
  <header class="topbar">
    <div class="inner">
      <RouterLink class="brand" to="/">{{ store.siteTitle }}</RouterLink>
      <nav>
        <RouterLink to="/">الرئيسية</RouterLink>
        <RouterLink to="/orders">الطلبات</RouterLink>
        <RouterLink to="/production">الإنتاج</RouterLink>
        <RouterLink to="/materials">المواد</RouterLink>
        <RouterLink to="/templates">القوالب</RouterLink>
        <RouterLink to="/about">عن المنصة</RouterLink>
        <!-- المفتاح نفسه يحكم لوحة Django: الاختيار محفوظ في المتصفح بالمفتاح الذي تقرؤه اللوحة. -->
        <button type="button" class="btn theme-switch" :aria-label="`وضع الألوان: ${THEME_LABELS[theme.theme]}. اضغط للتبديل`" @click="theme.cycle">
          الوضع: {{ THEME_LABELS[theme.theme] }}
        </button>
        <!-- لوحة Django صفحة يخدمها الخادم لا مسار في الواجهة: رابط عادي بتحميل كامل. -->
        <a v-if="session.user?.admin_url" :href="session.user.admin_url">لوحة الإدارة</a>
        <template v-if="session.user">
          <span class="who">{{ session.user.username }}</span>
          <button type="button" class="btn" :disabled="leaving" @click="logout">خروج</button>
        </template>
        <RouterLink v-else-if="session.checked" to="/login">دخول</RouterLink>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <RouterView />
  </main>
</template>

<style scoped>
.who { color: var(--muted); font-size: 15px; }
.theme-switch { padding-inline: 12px; font-size: 15px; color: var(--muted); }
</style>
