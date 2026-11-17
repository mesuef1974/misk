<script setup lang="ts">
// لوح الواجهة في صفحتَي الزائر والدخول: نصف الصفحة بلون السمة وعليه نقش الهوية، وفي وسطه بطاقة عاجية
// تحمل شعار الشريط بلون السمة والشعار اللفظي. زينة لا محتوى: مخفي عن قارئ الشاشة وعن الجوال.
import BrandRibbonLogo from "@/components/BrandRibbonLogo.vue";
</script>

<template>
  <div class="brand-panel" aria-hidden="true">
    <div class="card">
      <BrandRibbonLogo :height="150" />
      <p>يُرسم اسمك ثم يُحفر</p>
    </div>
  </div>
</template>

<style scoped>
/* اللوح بلون السمة النهاري في الوضعين، والبطاقة عاجية فيهما: كبطاقة إهداء على ورق ملوَّن. */
.brand-panel {
  position: relative; isolation: isolate; overflow: hidden;
  display: grid; place-items: center; min-block-size: 360px; padding: 32px;
  border-radius: calc(var(--radius) * 4); background: var(--day-accent);
}
.brand-panel::before {
  content: ""; position: absolute; inset: 0; z-index: -1;
  background: color-mix(in srgb, var(--ivory) 16%, transparent);
  -webkit-mask: url("../static/brand/motif-mono.svg") top center / 150px auto repeat;
  mask: url("../static/brand/motif-mono.svg") top center / 150px auto repeat;
}
.card {
  display: grid; justify-items: center; gap: 14px; inline-size: min(100%, 380px); padding: 40px 28px 30px;
  border-radius: calc(var(--radius) * 4); background: var(--ivory);
  box-shadow: 0 18px 48px color-mix(in srgb, var(--day-ink) 35%, transparent);
}
.card p { margin: 0; color: var(--day-accent); font-family: var(--font-heading); font-size: 18px; font-weight: 500; }
@media (max-width: 860px) { .brand-panel { display: none; } }
</style>
