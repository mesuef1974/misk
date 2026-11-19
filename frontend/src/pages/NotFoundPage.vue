<template>
  <h1>الصفحة غير موجودة</h1>
  <div class="empty">
    <div class="inner">
      <div class="mark" aria-hidden="true"></div>
      <p>لا صفحة بهذا العنوان. لعل الرابط قديم أو فيه خطأ.</p>
      <RouterLink class="btn primary home" :to="{ name: 'home' }">الصفحة الرئيسية</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.home { margin-block-start: 16px; }
</style>
