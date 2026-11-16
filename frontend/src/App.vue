<script setup lang="ts">
import { onMounted } from "vue";
import { useAppStore } from "@/stores/app";

const store = useAppStore();
onMounted(() => store.loadPing());
</script>

<template>
  <header class="topbar">
    <div class="inner">
      <RouterLink class="brand" to="/">{{ store.siteTitle }}</RouterLink>
      <nav>
        <RouterLink to="/">الرئيسية</RouterLink>
        <RouterLink to="/about">عن المنصة</RouterLink>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <RouterView />
  </main>
</template>
