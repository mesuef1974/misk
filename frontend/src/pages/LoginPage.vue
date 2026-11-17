<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { errorMessage } from "@/api/client";
import BrandPanel from "@/components/BrandPanel.vue";
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
  <!-- صفحة مقسومة: النموذج في نصف ولوح الهوية بلون السمة في النصف الآخر (يختفي على الجوال). -->
  <div class="login-split">
  <div class="login-side">
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
  </div>
  <BrandPanel />
  </div>
</template>

<style scoped>
.login-split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; align-items: stretch; min-block-size: min(560px, calc(100vh - 104px)); }
.login-side { display: flex; flex-direction: column; justify-content: center; }
@media (max-width: 860px) { .login-split { grid-template-columns: 1fr; min-block-size: 0; } }
.login { display: grid; gap: 16px; inline-size: 100%; max-inline-size: 420px; }
.login .btn { justify-self: start; }
</style>
