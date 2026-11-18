# مسك

Django 5 + Django Ninja (API تحت `/api/`) + Vue 3 (Vite، Pinia، TypeScript) تُحقن عبر django-vite في `templates/spa.html`.
PostgreSQL + Redis + Celery (`config/celery.py`). النشر على Railway (`.railway/railway.ts`، يُطبَّق بـ `railway config apply` من طرفية المالك).

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
- لا `gh pr merge` ولا `railway` ولا `merge_gate.py --enable` من الجلسة: محجوبة بـ deny في `.claude/settings.json`؛ الدمج والنشر بيد المالك.
- لا `git push` إلا بأمر المالك. `.claude/hooks/guard_git.py` يحجب الدفع إلى main والدفع القسري و`git add -A` وتجاوز فحوص الإيداع؛ دفع فرع العمل غير محجوب تقنيًّا.
- سطر الاعتماد «اعتُمد من المالك — …» لا تكتبه الجلسة إلا بأمر المالك الصريح لكل رأس: الفحص لا يميّز كاتبه.
- لا تعديل على `.github/`، `scripts/*gate*`, `security/`, lockfiles, `Dockerfile`, `.railway/` داخل بطاقة عادية.

## أوامر
```bash
python manage.py runserver            # 8000
npm --prefix frontend run dev          # 5173 (HMR عبر django-vite)
python scripts/prepush_check.py --frontend
python automation/ledger.py list
```
