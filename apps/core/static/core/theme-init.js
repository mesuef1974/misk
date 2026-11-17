// يضع الوضع والسمة المحفوظين على <html> قبل رسم الصفحة كي لا تومض المنصة بوضع النظام أو بالسمة الافتراضية ثم تنقلب.
// المفتاح والقيم هي ما تكتبه لوحة Django (admin/js/theme.js) والمنصة (frontend/src/domain/theme.ts).
// ملف ثابت لا سكربت مضمَّن: يوافق سياسة CSP. تحمّله المنصة ولوحة Django كلتاهما.
(function () {
  "use strict";
  // أسماء السمات كما في frontend/src/static/brand/tokens.css وdomain/theme.ts (tests/test_brand.py يطابقها).
  var palettes = ["navy", "royal-blue", "teal", "emerald", "olive", "purple", "rose", "chocolate", "black", "oud"];
  var theme = "auto";
  var palette = "oud";
  try {
    var stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") theme = stored;
    var storedPalette = localStorage.getItem("palette");
    if (palettes.indexOf(storedPalette) !== -1) palette = storedPalette;
  } catch (e) {
    // التخزين محجوب: يبقى الوضع تلقائيًّا والسمة الافتراضية.
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.palette = palette;
})();
