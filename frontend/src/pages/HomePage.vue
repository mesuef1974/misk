<script setup lang="ts">
import { useAppStore } from "@/stores/app";
import StatusCard from "@/components/StatusCard.vue";

const store = useAppStore();
</script>

<template>
  <h1>{{ store.siteTitle }}</h1>
  <p class="lead">Django + Vue 3 + PostgreSQL على Railway، مع أتمتة التطوير مدمجة.</p>
  <StatusCard :ok="store.backendOk" />
</template>
