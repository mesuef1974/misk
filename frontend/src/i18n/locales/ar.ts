// المصدر: مفاتيح هذا الملف هي المخطّط، وen.ts ملزَم بها نوعًا (Messages) فلا تنقص ترجمة ولا تزيد.
// نصوص القشرة والصفحات العامة والتسميات المشتركة هنا؛ نصوص كل قسم من الورشة في ملفه تحت `ar/`.

import catalog from "./ar/catalog";
import orders from "./ar/orders";
import production from "./ar/production";
import store from "./ar/store";

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
    about: "من نحن",
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
  store,
  about: {
    heading: "من نحن",
    lead: "مسك ديزاين ورشة حفر بالليزر في قطر: يُرسم اسمك ثم يُحفر على الجلد والخشب والأكريليك.",
    steps: {
      design: {
        title: "ترى قبل أن تدفع.",
        body: "المعاينة في صفحة المنتج هي ملف الحفر نفسه، بالخط والمقاس اللذين يخرجان من الورشة.",
      },
      make: {
        title: "نحفر عند الطلب.",
        body: "كل قطعة تُصنع لصاحبها بعد الدفع، وموعد جاهزيتها محسوب من طابور الورشة الفعلي.",
      },
      receive: {
        title: "تتابع طلبك.",
        body: "رابط تتبّع خاص يريك مرحلة الطلب، ومنه تحجز موعد الاستلام.",
      },
    },
    audit: "ما تقرّه في المعاينة هو ما نحفره، ونترك الخامة الطبيعية تظهر بلونها وملمسها.",
  },
  notFound: {
    heading: "الصفحة غير موجودة",
    body: "لا صفحة بهذا العنوان. لعل الرابط قديم أو فيه خطأ.",
    home: "الصفحة الرئيسية",
  },
};

export default ar;
