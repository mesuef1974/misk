<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { errorMessage } from "@/api/client";
import BrandIcon from "@/components/BrandIcon.vue";
import BrandLogo from "@/components/BrandLogo.vue";
import LiveNotice from "@/components/LiveNotice.vue";
import ThemePicker from "@/components/ThemePicker.vue";
import { useAppStore } from "@/stores/app";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { useSessionStore } from "@/stores/session";
import { useThemeStore } from "@/stores/theme";

const store = useAppStore();
const session = useSessionStore();
const theme = useThemeStore();
const router = useRouter();
const leaving = ref(false);
const logoutError = ref("");

onMounted(() => {
  store.loadPing();
  session.ensureChecked();
  window.addEventListener("storage", theme.onStorage);
});
// تنبيه «لم يتم الخروج» يخصّ المحاولة التي سبّبته: لا يبقى قديمًا بعد الانتقال إلى صفحة أخرى.
// يُمسح عند بدء الانتقال لا نهايته: انتقال بطيء بدأ قبل المحاولة لا يمسح تنبيهها حين ينتهي بعدها.
const stopClearingLogoutError = router.beforeEach(() => {
  logoutError.value = "";
});
onBeforeUnmount(() => {
  window.removeEventListener("storage", theme.onStorage);
  stopClearingLogoutError();
});

async function logout(): Promise<void> {
  leaving.value = true;
  logoutError.value = "";
  try {
    await session.logout();
    // بيانات المشرف لا تبقى في الذاكرة بعد الخروج.
    useOrdersStore().clear();
    useProductionStore().clear();
    useCatalogStore().clear();
    await router.push({ name: "login" });
  } catch (error) {
    // تعذّر الوصول إلى الخادم: الجلسة ما زالت قائمة والزر يبقى ظاهرًا لإعادة المحاولة.
    logoutError.value = `لم يتم الخروج: ${errorMessage(error)}`;
  } finally {
    leaving.value = false;
  }
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <!-- الشعار مسارات بلا نص حي: الاسم المقروء على الرابط نفسه. وهو رابط الرئيسية. -->
      <RouterLink class="brand" to="/" :aria-label="store.siteTitle"><BrandLogo class="sima-mark-intro" :height="36" /></RouterLink>
      <nav class="main" aria-label="أقسام المنصة">
        <RouterLink class="nav-item" to="/orders"><BrandIcon name="order" /><span>الطلبات</span></RouterLink>
        <RouterLink class="nav-item" to="/production"><BrandIcon name="laser" /><span>الإنتاج</span></RouterLink>
        <RouterLink class="nav-item" to="/materials"><BrandIcon name="leather" /><span>المواد</span></RouterLink>
        <RouterLink class="nav-item" to="/templates"><BrandIcon name="name" /><span>القوالب</span></RouterLink>
      </nav>
      <nav class="aux" aria-label="الحساب والإعدادات">
        <RouterLink class="nav-item" to="/about">عن المنصة</RouterLink>
        <!-- المفتاحان نفساهما يحكمان لوحة Django: الاختيار محفوظ في المتصفح بما تقرؤه اللوحة. -->
        <ThemePicker />
        <!-- لوحة Django صفحة يخدمها الخادم لا مسار في الواجهة: رابط عادي بتحميل كامل. -->
        <a v-if="session.user?.admin_url" class="nav-item" :href="session.user.admin_url">لوحة الإدارة</a>
        <template v-if="session.user">
          <button type="button" class="nav-item" :disabled="leaving" @click="logout">خروج</button>
          <LiveNotice class="logout-error" :message="logoutError" />
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
      <div class="print-only print-head" aria-hidden="true"><BrandLogo :height="48" /></div>
      <RouterView />
      <div class="print-only print-foot" aria-hidden="true"><span>يُرسم اسمك ثم يُحفر</span></div>
    </main>
  </div>
</template>
