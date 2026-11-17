# مسك

Django 5 + Django Ninja (API تحت `/api/`) + Vue 3 (Vite، Pinia، TypeScript) تُحقن عبر django-vite في `templates/spa.html`.
PostgreSQL + Redis + Celery (`config/celery.py`). النشر على Railway (`railway.toml`).

## البنية
- `config/` إعدادات (base/development/production/testing)، `apps/<app>/` كل تطبيق: `models.py` نحيل، `services.py` كتابة،
  `selectors.py` قراءة، `api.py` مسارات Ninja، `tests/`.
- `frontend/src/`: `pages/` (lazy)، `components/`، `stores/` (Pinia)، `api/client.ts` (جلسة + CSRF، لا توكنات في localStorage).
- `scripts/` بوابات، `automation/` دفتر البطاقات والمشغّل، `security/sensitive_paths.json` المسارات الحسّاسة.

## قواعد
- DDD + Clean Architecture + SOLID. ORM فقط. Skinny Models / Fat Services. idempotent. > 300ms → مهمة خلفية.
- RTL-first بخصائص منطقية. Lazy loading. لا `**`/`###` مبالَغ في الوثائق.
- أمن: جلسات HttpOnly+Secure+SameSite، RBAC، Audit Trail (`apps.core.models.AuditLog`)، لا أسرار في الشيفرة.
- كل تغيير نماذج يرافقه `makemigrations`؛ هجرات expand/contract لا هدم.
- قبل أي دفع: `python scripts/prepush_check.py`.

## ما لا تفعله
- لا `gh pr merge` المباشر ولا `railway` من الجلسة (`.claude/settings.json` يحجبهما). الدفع إلى فرع الطلب بأمر المالك.
- الدمج من الجلسة بطريق واحد (قرار المالك 2026-11-17): `python scripts/merge_gate.py <رقم> --repo <owner/name> --merge`.
  يدمج بالضغط إن اعتمد المالك رأس الطلب واخضرّت الفحوص وكان خارج نافذة النشر، ويرفض ما يمسّ المال
  أو المسارات الحسّاسة (`security/sensitive_paths.json`) أو البوابات نفسها: تلك تبقى بزر المالك. لا تلتفّ على رفضه.
- لا تعديل على `.github/`، `scripts/*gate*`, `security/`, lockfiles, `Dockerfile`, `railway.toml` داخل بطاقة عادية.

## أوامر
```bash
python manage.py runserver            # 8000
npm --prefix frontend run dev          # 5173 (HMR عبر django-vite)
python scripts/prepush_check.py --frontend
python automation/ledger.py list
```
