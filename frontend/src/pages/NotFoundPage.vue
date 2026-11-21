<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { localeParam } from "@/domain/locale";
import { currentLocale } from "@/i18n";

const { t } = useI18n();
</script>

<template>
  <h1>{{ t("notFound.heading") }}</h1>
  <div class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>{{ t("notFound.body") }}</p>
      <!-- هذا المسار خارج الأب ذي معامل اللغة فلا يحمله التنقّل بالاسم: يُعطى صراحةً ليبقى الزائر في لغته. -->
      <RouterLink class="btn primary home" :to="{ name: 'home', params: { locale: localeParam(currentLocale()) } }">
        {{ t("notFound.home") }}
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.home { margin-block-start: 16px; }
</style>
