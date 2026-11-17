<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import BrandIcon from "@/components/BrandIcon.vue";
import BrandLockup from "@/components/BrandLockup.vue";
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
  <div class="shell">
    <aside class="side">
      <!-- الشعار مسارات بلا نص حي: الاسم المقروء على الرابط نفسه. وهو رابط الرئيسية. -->
      <RouterLink class="brand" to="/" :aria-label="store.siteTitle"><BrandLockup class="sima-mark-intro" :height="36" /></RouterLink>
      <nav class="main" aria-label="أقسام المنصة">
        <RouterLink class="nav-item" to="/orders"><BrandIcon name="order" /><span>الطلبات</span></RouterLink>
        <RouterLink class="nav-item" to="/production"><BrandIcon name="laser" /><span>الإنتاج</span></RouterLink>
        <RouterLink class="nav-item" to="/materials"><BrandIcon name="leather" /><span>المواد</span></RouterLink>
        <RouterLink class="nav-item" to="/templates"><BrandIcon name="name" /><span>القوالب</span></RouterLink>
      </nav>
      <nav class="aux" aria-label="الحساب والإعدادات">
        <RouterLink class="nav-item" to="/about">عن المنصة</RouterLink>
        <!-- المفتاح نفسه يحكم لوحة Django: الاختيار محفوظ في المتصفح بالمفتاح الذي تقرؤه اللوحة. -->
        <button type="button" class="nav-item theme-switch" :aria-label="`وضع الألوان: ${THEME_LABELS[theme.theme]}. اضغط للتبديل`" @click="theme.cycle">
          الوضع: {{ THEME_LABELS[theme.theme] }}
        </button>
        <!-- لوحة Django صفحة يخدمها الخادم لا مسار في الواجهة: رابط عادي بتحميل كامل. -->
        <a v-if="session.user?.admin_url" class="nav-item" :href="session.user.admin_url">لوحة الإدارة</a>
        <template v-if="session.user">
          <button type="button" class="nav-item" :disabled="leaving" @click="logout">خروج</button>
          <div class="user">
            <span class="avatar" aria-hidden="true"></span>
            <div class="who"><b>{{ session.user.username }}</b><span class="muted">{{ store.siteTitle }}</span></div>
          </div>
        </template>
        <RouterLink v-else-if="session.checked" class="nav-item" to="/login">دخول</RouterLink>
      </nav>
    </aside>
    <main class="wrap">
      <!-- رأس الورقة المطبوعة وتذييلها كما في شاشة الطباعة من الدليل؛ لا يظهران على الشاشة. -->
      <div class="print-only print-head" aria-hidden="true"><BrandLockup :height="44" /></div>
      <RouterView />
      <div class="print-only print-foot" aria-hidden="true"><span>يُرسم اسمك ثم يُحفر</span></div>
    </main>
  </div>
</template>
