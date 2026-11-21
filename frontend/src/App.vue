<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { errorMessage } from "@/api/client";
import BrandIcon from "@/components/BrandIcon.vue";
import BrandLockup from "@/components/BrandLockup.vue";
import BrandLockupLatin from "@/components/BrandLockupLatin.vue";
import BrandMark from "@/components/BrandMark.vue";
import LiveNotice from "@/components/LiveNotice.vue";
import ThemePicker from "@/components/ThemePicker.vue";
import { localeParam, otherLocale, type Locale } from "@/domain/locale";
import { useAppStore } from "@/stores/app";
import { useCartStore } from "@/stores/cart";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { useSessionStore } from "@/stores/session";
import { useThemeStore } from "@/stores/theme";

const store = useAppStore();
const session = useSessionStore();
const theme = useThemeStore();
const cart = useCartStore();
const router = useRouter();
const route = useRoute();
const { t, locale } = useI18n();
const siteName = computed(() => store.title(locale.value as Locale));
// عنوان التبويب يتبع اللغة والاسم الآتي من الخادم.
watchEffect(() => {
  if (siteName.value) document.title = siteName.value;
});

// الصفحة نفسها باللغة الأخرى. «غير موجودة» بلا مسار مقابل فلا مبدِّل فيها.
const alternate = computed(() => {
  if (!route.meta.localized || !route.name) return null;
  const target = otherLocale(locale.value as Locale);
  return {
    lang: target,
    to: { name: route.name, params: { ...route.params, locale: localeParam(target) }, query: route.query, hash: route.hash },
  };
});
const leaving = ref(false);
const logoutError = ref("");

onMounted(() => {
  store.loadPing();
  session.ensureChecked();
  // عدد ما في السلة يظهر في الشريط من أي صفحة.
  void cart.ensureLoaded();
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
    logoutError.value = t("nav.logoutFailed", { reason: errorMessage(error) });
  } finally {
    leaving.value = false;
  }
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <!-- القفل (الرمز وكلمة «مسك») مسارات بلا نص حي: الاسم المقروء على الرابط نفسه. وهو رابط الرئيسية. -->
      <RouterLink class="brand" :to="{ name: 'home' }" :aria-label="siteName"><BrandLockupLatin v-if="locale === 'en'" class="sima-mark-intro" :height="36" /><BrandLockup v-else class="sima-mark-intro" :height="36" /></RouterLink>
      <!-- المشرف يرى أقسام الورشة، وغيره يرى المتجر. الحماية الفعلية في الخادم وحارس المسارات. -->
      <nav v-if="session.isStaff" class="main" :aria-label="t('nav.sections')">
        <RouterLink class="nav-item" :to="{ name: 'orders' }"><BrandIcon name="order" /><span>{{ t("nav.orders") }}</span></RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'production' }"><BrandIcon name="laser-engrave" /><span>{{ t("nav.production") }}</span></RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'materials' }"><BrandIcon name="leather" /><span>{{ t("nav.materials") }}</span></RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'templates' }"><BrandIcon name="name" /><span>{{ t("nav.templates") }}</span></RouterLink>
      </nav>
      <nav v-else class="main" :aria-label="t('nav.sections')">
        <RouterLink class="nav-item" :to="{ name: 'products' }"><BrandIcon name="favors" /><span>{{ t("store.nav.products") }}</span></RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'designs' }"><BrandIcon name="wood" /><span>{{ t("store.nav.designs") }}</span></RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'cart' }" :aria-label="cart.count ? t('store.nav.cartCount', { count: cart.count }) : undefined">
          <BrandIcon name="order" /><span>{{ t("store.nav.cart") }}</span><span v-if="cart.count" class="pill num count" aria-hidden="true">{{ cart.count }}</span>
        </RouterLink>
      </nav>
      <nav class="aux" :aria-label="t('nav.account')">
        <RouterLink v-if="session.isStaff" class="nav-item" :to="{ name: 'products' }">{{ t("store.nav.store") }}</RouterLink>
        <RouterLink class="nav-item" :to="{ name: 'about' }">{{ t("nav.about") }}</RouterLink>
        <!-- اسم اللغة الأخرى بلغتها هي (lang عليه)، ووجهته الصفحة نفسها بتلك اللغة. -->
        <RouterLink v-if="alternate" class="nav-item" :to="alternate.to" :lang="alternate.lang" :aria-label="t('language.switchLabel')">
          {{ t("language.switchTo") }}
        </RouterLink>
        <!-- المفتاحان نفساهما يحكمان لوحة Django: الاختيار محفوظ في المتصفح بما تقرؤه اللوحة. -->
        <ThemePicker />
        <!-- لوحة Django صفحة يخدمها الخادم لا مسار في الواجهة: رابط عادي بتحميل كامل. -->
        <a v-if="session.user?.admin_url" class="nav-item" :href="session.user.admin_url">{{ t("nav.admin") }}</a>
        <template v-if="session.user">
          <button type="button" class="nav-item" :disabled="leaving" @click="logout">{{ t("nav.logout") }}</button>
          <LiveNotice class="logout-error" :message="logoutError" />
          <div class="user">
            <span class="avatar" aria-hidden="true"></span>
            <div class="who"><b>{{ session.user.username }}</b><span class="muted">{{ siteName }}</span></div>
          </div>
        </template>
        <RouterLink v-else-if="session.checked" class="nav-item" :to="{ name: 'login' }">{{ t("nav.login") }}</RouterLink>
      </nav>
    </aside>
    <main class="wrap">
      <!-- رأس الورقة المطبوعة وتذييلها كما في شاشة الطباعة من الدليل؛ لا يظهران على الشاشة. -->
      <div class="print-only print-head" aria-hidden="true"><BrandMark :size="48" /></div>
      <RouterView />
      <!-- صفحات الثقة في تذييل كل صفحة يراها الزائر. -->
      <nav v-if="!session.isStaff" class="store-foot" :aria-label="t('store.nav.trust')">
        <RouterLink :to="{ name: 'faq' }">{{ t("store.nav.faq") }}</RouterLink>
        <RouterLink :to="{ name: 'returns' }">{{ t("store.nav.returns") }}</RouterLink>
        <RouterLink :to="{ name: 'privacy' }">{{ t("store.nav.privacy") }}</RouterLink>
        <RouterLink :to="{ name: 'terms' }">{{ t("store.nav.terms") }}</RouterLink>
      </nav>
      <div class="print-only print-foot" aria-hidden="true"><span>{{ t("site.slogan") }}</span></div>
    </main>
  </div>
</template>
