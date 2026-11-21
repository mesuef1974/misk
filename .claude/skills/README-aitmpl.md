# مهارات ووكلاء من aitmpl.com

المصدر: github.com/davila7/claude-code-templates (فرع main)، نُزِّلت في 2026-11-20.
قُرئ كل ملف كاملًا قبل التثبيت، فلم يوجد فيه حقن تعليمات ولا أوامر شبكة ولا قراءة أسرار.

التعديلات على الأصل:
- أُضيفت في رأس كل ملف «ملاحظة مسك»: السياق القطري، ومنع الأنماط المظلمة، وقيد عدم التسويق في مدارس المالك.
- حُذفت ادعاءات قدرات غير موجودة من paid-ads وpricing-strategy وreferral-program وsocial-content.
- حُذفت كلمة PROACTIVELY من أوصاف الوكلاء.
- مخرجات competitive-ads-extractor تُحفظ تحت `marketing/research/` داخل المشروع.
- حُذف سطر السكربت الغائب من i18n-localization.

المستبعد:
- twilio-communications: الملف الأصلي مبتور.
- django-developer وvue-expert: تخالف بنية المشروع (DRF و«Fat models» وNuxt).
- payment-integration: عامة حول Stripe ولا تناسب بوابات قطر.
- خوادم MCP للإعلانات والنشر: تحتاج إذن المالك لكل حساب.

الوكلاء في `.claude/agents/`: market-researcher، competitive-analyst، trend-analyst، ux-researcher، content-marketer، legal-advisor، compliance-auditor، schema-migration-specialist.
