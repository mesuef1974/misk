<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import BrandIcon from "@/components/BrandIcon.vue";
import StatusCard from "@/components/StatusCard.vue";
import { ORDER_STATUSES, STATUS_LABELS } from "@/domain/orders";
import { useAppStore } from "@/stores/app";
import { useCatalogStore } from "@/stores/catalog";
import { useOrdersStore } from "@/stores/orders";
import { useProductionStore } from "@/stores/production";
import { useSessionStore } from "@/stores/session";

const store = useAppStore();
const session = useSessionStore();
const orders = useOrdersStore();
const production = useProductionStore();
const catalog = useCatalogStore();

/** الحالات المفتوحة فقط: ما يحتاج عملًا اليوم، لا ما سُلِّم أو أُلغي. */
const OPEN = ["draft", "confirmed", "in_production", "ready"] as const satisfies readonly (typeof ORDER_STATUSES)[number][];

const orderTiles = computed(() =>
  OPEN.map((status) => ({ status, label: STATUS_LABELS[status], count: orders.countByStatus[status] ?? 0 })),
);
const plannedSheets = computed(() => production.countByStatus.planned ?? 0);
const loadError = computed(() => orders.loadError || production.loadError || catalog.loadError);

function loadAll(): Promise<unknown> {
  return Promise.all([orders.load(), production.load(), catalog.load()]);
}

onMounted(async () => {
  await session.ensureChecked();
  if (session.isStaff) await loadAll();
});
// الدخول من هذه الصفحة نفسها لا يعيد تركيبها.
watch(
  () => session.isStaff,
  (isStaff) => {
    if (isStaff) void loadAll();
  },
);
</script>

<template>
  <template v-if="session.isStaff">
    <div class="page-head">
      <h1>{{ store.siteTitle }}</h1>
      <RouterLink class="btn primary" :to="{ name: 'order-new' }">طلب جديد</RouterLink>
    </div>

    <div v-if="loadError" class="notice" role="alert">
      {{ loadError }}
      <button type="button" class="btn retry" @click="loadAll()">إعادة المحاولة</button>
    </div>

    <section aria-labelledby="home-orders">
      <h2 id="home-orders">الطلبات المفتوحة</h2>
      <div class="tiles">
        <RouterLink v-for="tile in orderTiles" :key="tile.status" class="list-row tile" :to="{ name: 'orders' }">
          <BrandIcon name="order" />
          <span class="what"><b class="num">{{ orders.loaded ? tile.count : "—" }}</b><span class="muted">{{ tile.label }}</span></span>
        </RouterLink>
      </div>
    </section>

    <section aria-labelledby="home-work">
      <h2 id="home-work">الورشة</h2>
      <div class="tiles">
        <RouterLink class="list-row tile" :to="{ name: 'production' }">
          <BrandIcon name="laser" />
          <span class="what"><b class="num">{{ production.loaded ? plannedSheets : "—" }}</b><span class="muted">ألواح تنتظر التشغيل</span></span>
        </RouterLink>
        <RouterLink class="list-row tile" :to="{ name: 'materials' }">
          <BrandIcon name="leather" />
          <span class="what"><b class="num">{{ catalog.loaded ? catalog.materials.length : "—" }}</b><span class="muted">مواد</span></span>
        </RouterLink>
        <RouterLink class="list-row tile" :to="{ name: 'templates' }">
          <BrandIcon name="name" />
          <span class="what"><b class="num">{{ catalog.loaded ? catalog.templates.length : "—" }}</b><span class="muted">قوالب</span></span>
        </RouterLink>
      </div>
    </section>
  </template>

  <!-- صفحة الزائر على شاشة landing من الدليل: الشعار اللفظي، العنوان، الزران، بطاقات الشخصية، ولوح الرمز. -->
  <div v-else-if="session.checked" class="landing">
    <div class="pitch">
      <p class="slogan">يُرسم اسمك ثم يُحفر</p>
      <h1>اسمك، مرسومًا ثم محفورًا.</h1>
      <p class="lead">إدارة طلبات ورشة الليزر: الكتالوج، الطلبات، وتخطيط الألواح وتشغيلها.</p>
      <div class="cta">
        <RouterLink class="btn primary" :to="{ name: 'login' }">دخول المشرف</RouterLink>
        <RouterLink class="btn" :to="{ name: 'about' }">عن المنصة</RouterLink>
      </div>
      <div class="traits">
        <div class="panel"><h2>دقيقة</h2><p>نراجع إملاء كل اسم مع صاحبه قبل الحفر، ونذكر المقاس والخامة والعدد وموعد الاستلام بأرقامها.</p></div>
        <div class="panel"><h2>دافئة</h2><p>نسأل عن المناسبة وصاحبها قبل أن نقترح، ونترك الخامة الطبيعية تظهر بلونها وملمسها.</p></div>
        <div class="panel"><h2>أنيقة</h2><p>نختار للاسم خطًّا واحدًا يليق به ونترك حوله فراغًا، ونقول ما يلزم بجملة قصيرة.</p></div>
      </div>
    </div>
    <div class="showcase" aria-hidden="true"><div class="tile-mark"><div class="mark"></div></div></div>
  </div>

  <StatusCard class="status" :ok="store.backendOk" />
</template>

<style scoped>
h2 { font-size: 20px; margin-block: 0 12px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
.tile .what { display: flex; flex-direction: column; line-height: 1.4; }
.tile b { font-family: var(--font-heading); font-size: 26px; font-weight: 600; }
.tile .muted { font-size: 13px; }
.retry { margin-inline-start: 12px; }

.landing { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 32px; align-items: stretch; }
.pitch { display: flex; flex-direction: column; gap: 20px; padding-block: 24px; }
.pitch > * { margin: 0; }
.slogan { padding: 2px 10px; border-radius: 999px; background: var(--warm-soft); font-size: 13px; }
.pitch h1 { font-size: clamp(34px, 5vw, 56px); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; }
.traits { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-block-start: 12px; }
.traits h2 { margin-block-end: 6px; color: var(--accent); }
.traits p { margin: 0; color: var(--muted); font-size: 15px; }
.showcase { display: grid; place-items: center; min-block-size: 320px; border-radius: calc(var(--radius) * 2); background: var(--brand-soft); }
.tile-mark { display: grid; place-items: center; inline-size: min(60%, 260px); aspect-ratio: 1; border-radius: 28px; background: var(--bg); }
.tile-mark .mark {
  inline-size: 72%; aspect-ratio: 100 / 65.85071; background: var(--color-mark-ink);
  -webkit-mask: url("../static/brand/mark.svg") center / contain no-repeat;
  mask: url("../static/brand/mark.svg") center / contain no-repeat;
}
@media (max-width: 1180px) { .traits { grid-template-columns: 1fr; } }
@media (max-width: 860px) {
  .landing { grid-template-columns: 1fr; }
  .showcase { display: none; }
  /* الجوال في الدليل: العنوان والزر داخل بطاقة بلون العلامة. */
  .pitch { padding: 28px 24px; border-radius: 28px; background: var(--accent); color: var(--on-accent); }
  .pitch .slogan, .pitch .lead, .pitch .traits { display: none; }
  .pitch .btn { border-color: transparent; background: var(--bg); color: var(--ink); }
  .pitch .btn + .btn { background: transparent; border-color: var(--on-accent); color: var(--on-accent); }
}
</style>
