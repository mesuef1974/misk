<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import BrandIcon from "@/components/BrandIcon.vue";
import BrandLockupRibbon from "@/components/BrandLockupRibbon.vue";
import BrandPanel from "@/components/BrandPanel.vue";
import ProductCard from "@/components/ProductCard.vue";
import StatusCard from "@/components/StatusCard.vue";
import { ORDER_STATUSES, statusLabel } from "@/domain/orders";
import { useAppStore } from "@/stores/app";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { useSessionStore } from "@/stores/session";
import { useStorefrontStore } from "@/stores/storefront";

const { t } = useI18n();
const HOW = ["design", "pay", "receive"] as const;
const FEATURED = 3;
const store = useAppStore();
const session = useSessionStore();
const orders = useOrdersStore();
const production = useProductionStore();
const catalog = useCatalogStore();
const storefront = useStorefrontStore();
const featured = computed(() => storefront.templates.slice(0, FEATURED));

/** الحالات المفتوحة فقط: ما يحتاج عملًا اليوم، لا ما سُلِّم أو أُلغي. */
const OPEN = ["draft", "confirmed", "in_production", "ready"] as const satisfies readonly (typeof ORDER_STATUSES)[number][];

const orderTiles = computed(() =>
  OPEN.map((status) => ({ status, label: statusLabel(status), count: orders.countByStatus[status] ?? 0 })),
);
const plannedSheets = computed(() => production.countByStatus.planned ?? 0);
const loadError = computed(() => orders.loadError || production.loadError || catalog.loadError);

function loadAll(): Promise<unknown> {
  return Promise.all([orders.load(), production.load(), catalog.load()]);
}

onMounted(() => session.ensureChecked());
// مصدر واحد للتحميل: صار المستخدم مشرفًا عند التركيب، أو بعد التحقق من الجلسة، أو بالدخول من هذه الصفحة نفسها.
watch(
  () => session.isStaff,
  (isStaff) => {
    if (isStaff) void loadAll();
  },
  { immediate: true },
);
// الزائر يرى المتجر: منتجاته تُجلب حين يُعلم أنه ليس مشرفًا.
watch(
  () => session.checked && !session.isStaff,
  (visitor) => {
    if (visitor) void storefront.ensureLoaded();
  },
  { immediate: true },
);
</script>

<template>
  <template v-if="session.isStaff">
    <div class="page-head">
      <!-- الاسم قفلَ الهوية بإكساء الشريط بحبر السمة المختارة لا نصًّا؛ الاسم المقروء في aria-label. -->
      <h1 class="home-logo" :aria-label="store.siteTitle"><BrandLockupRibbon :height="88" /></h1>
      <RouterLink class="btn primary" :to="{ name: 'order-new' }">{{ t("dashboard.newOrder") }}</RouterLink>
    </div>

    <div v-if="loadError" class="notice" role="alert">
      {{ loadError }}
      <button type="button" class="btn retry" @click="loadAll()">{{ t("dashboard.retry") }}</button>
    </div>

    <section aria-labelledby="home-orders">
      <h2 id="home-orders">{{ t("dashboard.openOrders") }}</h2>
      <div class="tiles">
        <RouterLink v-for="tile in orderTiles" :key="tile.status" class="list-row tile" :to="{ name: 'orders' }">
          <BrandIcon name="order" />
          <span class="what"><b class="num">{{ orders.loaded ? tile.count : "—" }}</b><span class="muted">{{ tile.label }}</span></span>
        </RouterLink>
      </div>
    </section>

    <section aria-labelledby="home-work">
      <h2 id="home-work">{{ t("dashboard.workshop") }}</h2>
      <div class="tiles">
        <RouterLink class="list-row tile" :to="{ name: 'production' }">
          <BrandIcon name="laser-engrave" />
          <span class="what"><b class="num">{{ production.loaded ? plannedSheets : "—" }}</b><span class="muted">{{ t("dashboard.plannedSheets") }}</span></span>
        </RouterLink>
        <RouterLink class="list-row tile" :to="{ name: 'materials' }">
          <BrandIcon name="leather" />
          <span class="what"><b class="num">{{ catalog.loaded ? catalog.materials.length : "—" }}</b><span class="muted">{{ t("dashboard.materials") }}</span></span>
        </RouterLink>
        <RouterLink class="list-row tile" :to="{ name: 'templates' }">
          <BrandIcon name="name" />
          <span class="what"><b class="num">{{ catalog.loaded ? catalog.templates.length : "—" }}</b><span class="muted">{{ t("dashboard.templates") }}</span></span>
        </RouterLink>
      </div>
    </section>
  </template>

  <!-- صفحة الزائر على شاشة landing من الدليل: الشعار اللفظي، العنوان، الزران، خطوات الطلب، ولوح الرمز؛ وتحتها منتجات المتجر. -->
  <template v-else-if="session.checked">
    <div class="landing">
      <div class="pitch">
        <p class="slogan">{{ t("site.slogan") }}</p>
        <h1>{{ t("store.home.heading") }}</h1>
        <p class="lead">{{ t("store.home.lead") }}</p>
        <div class="cta">
          <RouterLink class="btn primary" :to="{ name: 'products' }">{{ t("store.home.browse") }}</RouterLink>
          <RouterLink class="btn" :to="{ name: 'about' }">{{ t("nav.about") }}</RouterLink>
        </div>
        <div class="traits" :aria-label="t('store.home.how.title')">
          <div v-for="step in HOW" :key="step" class="panel">
            <h2>{{ t(`store.home.how.${step}.title`) }}</h2>
            <p>{{ t(`store.home.how.${step}.body`) }}</p>
          </div>
        </div>
      </div>
      <BrandPanel />
    </div>

    <section v-if="featured.length" aria-labelledby="home-featured">
      <div class="featured-head">
        <h2 id="home-featured">{{ t("store.home.featured") }}</h2>
        <RouterLink :to="{ name: 'products' }">{{ t("store.home.allProducts") }}</RouterLink>
      </div>
      <ul class="product-grid">
        <li v-for="product in featured" :key="product.slug"><ProductCard :product="product" /></li>
      </ul>
    </section>
  </template>

  <StatusCard class="status" :ok="store.backendOk" />
</template>

<style scoped>
h2 { font-size: 20px; margin-block: 0 12px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.tile .what { display: flex; flex-direction: column; line-height: 1.4; }
.tile b { font-family: var(--font-heading); font-size: 26px; font-weight: 600; }
.tile .muted { font-size: 13px; }
.retry { margin-inline-start: 12px; }
.featured-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 16px; margin-block-end: 12px; }
.featured-head h2 { margin: 0; }

.landing { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 32px; align-items: stretch; }
.pitch { display: flex; flex-direction: column; gap: 20px; padding-block: 24px; }
.pitch > * { margin: 0; }
.slogan { align-self: flex-start; padding: 2px 10px; border-radius: 999px; background: var(--warm-soft); font-size: 13px; }
.pitch h1 { font-size: clamp(34px, 5vw, 56px); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; }
.traits { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-block-start: 12px; }
.traits h2 { margin-block-end: 6px; color: var(--accent); }
.traits p { margin: 0; color: var(--muted); font-size: 15px; }
@media (max-width: 1180px) { .traits { grid-template-columns: 1fr; } }
@media (max-width: 860px) {
  .landing { grid-template-columns: 1fr; }
  /* الجوال في الدليل: العنوان والزر داخل بطاقة بلون العلامة. */
  .pitch { padding: 28px 22px; border-radius: calc(var(--radius) * 3); background: var(--accent); color: var(--on-accent); }
  .pitch h1 { font-size: 28px; }
  .pitch .slogan, .pitch .lead, .pitch .traits { display: none; }
  .pitch .btn { border-color: transparent; background: var(--bg); color: var(--accent); }
  .pitch .btn + .btn { background: transparent; border-color: var(--on-accent); color: var(--on-accent); }
}
</style>
