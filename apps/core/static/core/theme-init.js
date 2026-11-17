// يضع الوضع المحفوظ على <html> قبل رسم الصفحة كي لا تومض المنصة بوضع النظام ثم تنقلب.
// المفتاح والقيم هي ما تكتبه لوحة Django (admin/js/theme.js) والمنصة (frontend/src/domain/theme.ts).
// ملف ثابت لا سكربت مضمَّن: يوافق سياسة CSP.
(function () {
  "use strict";
  var theme = "auto";
  try {
    var stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") theme = stored;
  } catch (e) {
    // التخزين محجوب: يبقى الوضع تلقائيًّا.
  }
  document.documentElement.dataset.theme = theme;
})();
