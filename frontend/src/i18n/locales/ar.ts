// المصدر: مفاتيح هذا الملف هي المخطّط، وen.ts ملزَم بها نوعًا (Messages) فلا تنقص ترجمة ولا تزيد.
// نصوص القشرة والصفحات العامة والتسميات المشتركة هنا؛ نصوص كل قسم من الورشة في ملفه تحت `ar/`.

import catalog from "./ar/catalog";
import orders from "./ar/orders";
import production from "./ar/production";

const ar = {
  site: {
    slogan: "يُرسم اسمك ثم يُحفر",
  },
  language: {
    // اسم اللغة الأخرى بلغتها هي، كما يبحث عنه قارئها.
    switchTo: "English",
    switchLabel: "Switch to English",
  },
  nav: {
    sections: "أقسام المنصة",
    account: "الحساب والإعدادات",
    orders: "الطلبات",
    production: "الإنتاج",
    materials: "المواد",
    templates: "القوالب",
    about: "عن المنصة",
    admin: "لوحة الإدارة",
    login: "دخول",
    logout: "خروج",
    logoutFailed: "لم يتم الخروج: {reason}",
  },
  status: {
    checking: "يتحقق من الخادم…",
    up: "الخادم يعمل",
    down: "الخادم لا يستجيب",
  },
  home: {
    heading: "اسمك، مرسومًا ثم محفورًا.",
    lead: "إدارة طلبات ورشة الليزر: الكتالوج، الطلبات، وتخطيط الألواح وتشغيلها.",
    staffLogin: "دخول المشرف",
    traits: {
      precise: {
        title: "دقيقة",
        body: "نراجع إملاء كل اسم مع صاحبه قبل الحفر، ونذكر المقاس والخامة والعدد وموعد الاستلام بأرقامها.",
      },
      warm: {
        title: "دافئة",
        body: "نسأل عن المناسبة وصاحبها قبل أن نقترح، ونترك الخامة الطبيعية تظهر بلونها وملمسها.",
      },
      elegant: {
        title: "أنيقة",
        body: "نختار للاسم خطًّا واحدًا يليق به ونترك حوله فراغًا، ونقول ما يلزم بجملة قصيرة.",
      },
    },
  },
  // رئيسية المشرف.
  dashboard: {
    newOrder: "طلب جديد",
    retry: "إعادة المحاولة",
    openOrders: "الطلبات المفتوحة",
    workshop: "الورشة",
    plannedSheets: "ألواح تنتظر التشغيل",
    materials: "مواد",
    templates: "قوالب",
  },
  errors: {
    network: "تعذّر الاتصال. تحقّق من الشبكة ثم أعد المحاولة",
    unauthorized: "يلزم تسجيل الدخول بحساب مشرف",
    forbidden: "لا صلاحية لهذا الإجراء",
    notFound: "غير موجود",
    tooMany: "محاولات كثيرة؛ حاول بعد قليل",
    failed: "تعذّر إتمام العملية ({status})",
    unexpected: "حدث خطأ غير متوقع",
  },
  // تسميات مشتركة بين صفحات الورشة.
  currency: "ر.ق",
  orderStatus: {
    draft: "مسودة",
    awaiting_payment: "بانتظار الدفع",
    paid: "مدفوع",
    under_review: "قيد المراجعة",
    confirmed: "مؤكَّد",
    in_production: "قيد التنفيذ",
    ready: "جاهز",
    out_for_delivery: "في الطريق",
    ready_for_pickup: "جاهز للاستلام",
    delivered: "مُسلَّم",
    cancelled: "ملغى",
    refunded: "مُستردّ",
  },
  // نص الزر الذي ينقل الطلب إلى الحالة.
  orderAction: {
    under_review: "تحويل للمراجعة",
    confirmed: "تأكيد الطلب",
    in_production: "بدء التنفيذ",
    ready: "جاهز للتسليم",
    out_for_delivery: "خرج للتوصيل",
    ready_for_pickup: "جاهز للاستلام",
    delivered: "تسليم للعميل",
    cancelled: "إلغاء الطلب",
  },
  login: {
    heading: "تسجيل الدخول",
    username: "اسم المستخدم",
    passLabel: "كلمة المرور",
    checking: "يتحقق…",
    submit: "دخول",
  },
  theme: {
    button: "المظهر",
    buttonLabel: "المظهر: السمة {palette}، الوضع {mode}. اضغط للتغيير",
    dialog: "مظهر المنصة",
    palette: "السمة",
    mode: "الوضع",
    hint: "لكل سمة نهارها وليلها.",
    modes: { auto: "تلقائي", light: "نهاري", dark: "ليلي" },
    palettes: {
      navy: "كحلي",
      "royal-blue": "أزرق ملكي",
      teal: "فيروزي",
      emerald: "زمردي",
      olive: "زيتوني",
      purple: "بنفسجي",
      rose: "وردي",
      chocolate: "شوكولاتي",
      black: "أسود",
      oud: "عودي",
    },
  },
  orders,
  production,
  catalog,
  about: {
    heading: "عن المنصة",
    lead: "مسك تدير عمل ورشة ليزر صغيرة من الطلب إلى القطعة المنفَّذة.",
    steps: {
      catalog: {
        title: "الكتالوج.",
        body: "المواد بسماكاتها وكلفة ألواحها، ومعايرة كل مادة من قصاصة اختبار، وقوالب المنتجات بحقولها التي يملؤها الطلب.",
      },
      orders: {
        title: "الطلبات.",
        body: "الطلب يُحفظ مسودةً ثم يُؤكَّد، ولا يُؤكَّد قبل معايرة كل مادة فيه.",
      },
      production: {
        title: "الإنتاج.",
        body: "قطع الطلبات المؤكَّدة تُرتَّب على ألواح المادة، ثم يُسجَّل تشغيل كل لوح بمدته ونتيجته وكلفة مادته.",
      },
    },
    audit: "كل عملية كتابة تُسجَّل في سجل التدقيق، والدخول لحسابات المشرفين وحدها.",
  },
  notFound: {
    heading: "الصفحة غير موجودة",
    body: "لا صفحة بهذا العنوان. لعل الرابط قديم أو فيه خطأ.",
    home: "الصفحة الرئيسية",
  },
};

export default ar;
