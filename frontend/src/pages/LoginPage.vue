<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { errorMessage } from "@/api/client";
import { safeNext } from "@/domain/navigation";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const route = useRoute();
const router = useRouter();

const username = ref("");
const password = ref("");
const busy = ref(false);
const failure = ref("");

async function submit(): Promise<void> {
  if (busy.value || !username.value.trim() || !password.value) return;
  failure.value = "";
  busy.value = true;
  try {
    await session.login(username.value.trim(), password.value);
    await router.replace(safeNext(route.query.next));
  } catch (error) {
    failure.value = errorMessage(error);
  } finally {
    // كلمة المرور لا تبقى في الذاكرة بعد المحاولة، نجحت أو فشلت.
    password.value = "";
    busy.value = false;
  }
}
</script>

<template>
  <h1>تسجيل الدخول</h1>
  <form class="panel login" novalidate @submit.prevent="submit">
    <label class="field">
      <span>اسم المستخدم</span>
      <input v-model="username" type="text" name="username" autocomplete="username" maxlength="150" required dir="ltr" />
    </label>
    <label class="field">
      <span>كلمة المرور</span>
      <input
        v-model="password"
        type="password"
        name="password"
        autocomplete="current-password"
        maxlength="128"
        required
        dir="ltr"
      />
    </label>
    <div v-if="failure" class="notice" role="alert">{{ failure }}</div>
    <button type="submit" class="btn primary" :disabled="busy || !username.trim() || !password">
      {{ busy ? "يتحقق…" : "دخول" }}
    </button>
  </form>
</template>

<style scoped>
.login { display: grid; gap: 16px; max-inline-size: 420px; }
.login .btn { justify-self: start; }
</style>
