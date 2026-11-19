<script setup lang="ts">
/** منطقة إعلان حيّة: العنصر قائم في الصفحة قبل الرسالة، فقارئ الشاشة يعلن تغيّر نصّها.
 *  منطقة تُنشأ مع نصّها (v-if) لا يعلنها أغلب القرّاء. */
withDefaults(defineProps<{ message: string; kind?: "alert" | "status" }>(), { kind: "alert" });
</script>

<template>
  <div :role="kind" :class="message ? ['notice', { ok: kind === 'status' }] : 'idle'">{{ message }}</div>
</template>

<style scoped>
/* فارغة: خارج تدفّق التخطيط فلا تشغل خانة ولا فجوة، وباقية في شجرة الوصول. */
.idle { position: absolute; }
</style>
