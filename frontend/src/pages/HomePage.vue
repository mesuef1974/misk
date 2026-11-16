<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
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
  <h1>{{ store.siteTitle }}</h1>

  <template v-if="session.isStaff">
    <div v-if="loadError" class="notice" role="alert">
      {{ loadError }}
      <button type="button" class="btn retry" @click="loadAll()">إعادة المحاولة</button>
    </div>

    <section aria-labelledby="home-orders">
      <div class="section-head">
        <h2 id="home-orders">الطلبات المفتوحة</h2>
        <RouterLink class="btn primary" :to="{ name: 'order-new' }">طلب جديد</RouterLink>
      </div>
      <div class="tiles">
        <RouterLink v-for="tile in orderTiles" :key="tile.status" class="tile" :to="{ name: 'orders' }">
          <span class="count num">{{ orders.loaded ? tile.count : "—" }}</span>
          <span class="muted">{{ tile.label }}</span>
        </RouterLink>
      </div>
    </section>

    <section aria-labelledby="home-work">
      <div class="section-head">
        <h2 id="home-work">الورشة</h2>
      </div>
      <div class="tiles">
        <RouterLink class="tile" :to="{ name: 'production' }">
          <span class="count num">{{ production.loaded ? plannedSheets : "—" }}</span>
          <span class="muted">ألواح تنتظر التشغيل</span>
        </RouterLink>
        <RouterLink class="tile" :to="{ name: 'materials' }">
          <span class="count num">{{ catalog.loaded ? catalog.materials.length : "—" }}</span>
          <span class="muted">مواد</span>
        </RouterLink>
        <RouterLink class="tile" :to="{ name: 'templates' }">
          <span class="count num">{{ catalog.loaded ? catalog.templates.length : "—" }}</span>
          <span class="muted">قوالب</span>
        </RouterLink>
      </div>
    </section>
  </template>

  <template v-else-if="session.checked">
    <p class="lead">إدارة طلبات ورشة الليزر: الكتالوج، الطلبات، وتخطيط الألواح وتشغيلها.</p>
    <RouterLink class="btn primary" :to="{ name: 'login' }">دخول المشرف</RouterLink>
  </template>

  <StatusCard class="status" :ok="store.backendOk" />
</template>

<style scoped>
.section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; margin-block: 24px 12px; }
h2 { font-size: 20px; margin: 0; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.tile {
  display: flex; flex-direction: column; padding: 12px 16px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--surface); color: var(--ink); text-decoration: none; line-height: 1.5;
}
.tile:hover { border-color: var(--accent); }
.tile:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.count { font-size: 28px; font-weight: 700; }
.tile .muted { font-size: 15px; }
.status { margin-block-start: 32px; }
.retry { margin-inline-start: 12px; }
</style>
