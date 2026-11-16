<script setup lang="ts">
import { computed } from "vue";
import { groupPlacements } from "@/domain/production";
import type { Sheet } from "@/services/production";

const props = defineProps<{ sheet: Sheet }>();

const width = computed(() => Number(props.sheet.width_mm));
const height = computed(() => Number(props.sheet.height_mm));

/** القطع بإحداثيات اللوح (مم)، ورقم مجموعتها ليطابق مفتاح الرسم في الصفحة. */
const pieces = computed(() => {
  const numbers = new Map(groupPlacements(props.sheet).map((group) => [group.orderItemId, group.number]));
  return props.sheet.placements.map((placement) => {
    const w = Number(placement.width_mm);
    const h = Number(placement.height_mm);
    return {
      key: `${placement.order_item_id}-${placement.copy_index}`,
      x: Number(placement.x_mm),
      y: Number(placement.y_mm),
      w,
      h,
      number: numbers.get(placement.order_item_id) ?? 0,
      fontSize: Math.max(6, Math.min(w, h) * 0.45),
    };
  });
});
</script>

<template>
  <!-- إحداثيات الآلة من اليسار إلى اليمين مهما كان اتجاه الصفحة. -->
  <svg
    class="sheet"
    dir="ltr"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="`لوح ${sheet.id}: ${pieces.length} قطعة على ${sheet.width_mm} × ${sheet.height_mm} مم`"
  >
    <rect class="board" x="0" y="0" :width="width" :height="height" />
    <g v-for="piece in pieces" :key="piece.key">
      <rect class="piece" :x="piece.x" :y="piece.y" :width="piece.w" :height="piece.h" />
      <text
        :x="piece.x + piece.w / 2"
        :y="piece.y + piece.h / 2"
        :font-size="piece.fontSize"
        text-anchor="middle"
        dominant-baseline="central"
      >
        {{ piece.number }}
      </text>
    </g>
  </svg>
</template>

<style scoped>
.sheet { display: block; inline-size: 100%; block-size: auto; max-block-size: 360px; }
.board { fill: var(--bg); stroke: var(--line); stroke-width: 2; vector-effect: non-scaling-stroke; }
.piece { fill: color-mix(in srgb, var(--accent) 16%, var(--surface)); stroke: var(--accent); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
text { fill: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
