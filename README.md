# مسك

النشاط التجاري للحفر بالليزر في قطر: كفرات جلد طبيعي نباتي الدباغة، وتوزيعات المناسبات، على xTool P2S.

فُصل عن المحرّك التقني [local-pen-studio](https://github.com/mesuef1974/local-pen-studio) في 2026-11-16، وتاريخه منقول من مجلد `laser-cases/` هناك. المستودع عام: لا يدخله اسم زبون ولا رقم هاتف ولا سر، وكل ما فيه بيان شخصي يبقى محليًّا خارج git.

## الخلفية

Django 5.2 مع Django Ninja وPostgreSQL وRedis وCelery، من قالب `django_vue_railway`. واجهة Vue في `frontend/` هيكل فقط ولم تُبنَ بعد.

| التطبيق | ما فيه |
|---|---|
| `apps/core` | سجل التدقيق، ومصادقة الجلسة للمشرفين |
| `apps/catalog` | المواد، ومعايرتها من قصاصة الاختبار، وقوالب المنتجات بمخطط معاملاتها |
| `apps/orders` | الزبون والطلب وبنوده، وانتقالات الحالة |
| `apps/production` | ترتيب القطع على لوح 600 × 305، وسجل التشغيل |

كل تطبيق: `models.py` حقول وقيود، `domain.py` قواعد خالصة بلا Django، `services.py` الكتابة، `selectors.py` القراءة، `api.py` المسارات.

قواعد العمل المطبَّقة:
- إنشاء الطلب idempotent على `client_ref`، وقيم كل بند تُفحص على مخطط قالبه.
- لا يُؤكَّد طلب قبل أن تكون لكل مادة فيه معايرة من قصاصة اختبار.
- الحالة تتغير بانتقالات محددة: مسودة، مؤكَّد، قيد التنفيذ، جاهز، مُسلَّم؛ والإلغاء قبل الجاهزية.
- التخطيط يضع كل نسخة مرة واحدة، وإعادته لا تنشئ ألواحًا.
- سجل التشغيل يحفظ لقطة من الإعدادات والكلفة، وidempotent على `X-Request-ID`.

لم يُبنَ بعد: هاتف الزبون (ينتظر مكتبة تشفير)، وربط مولّدات SVG بالبنود، والواجهة.

## التشغيل محليًّا

```bash
cp .env.example .env
docker compose up -d db redis
uv venv .venv && uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

وثائق API على http://localhost:8000/api/docs/ ولوحة الإدارة على http://localhost:8000/admin/.

الفحص قبل الدفع (ruff، الهجرات، الأسرار، الاختبارات):

```bash
python scripts/prepush_check.py
```

النشر على Railway والأتمتة موصوفان في `CLAUDE.md` و`automation/README.md`، ولم يُفعَّل أيٌّ منهما.

## وثائق المشروع وعيّناته

- `laser-cases-brief.html`: ملخص الشريكين (الترخيص، السوق، الحساب، الخامات، التوريد).
- `laser/توزيعات_المناسبات.html`: الخط الثاني بالتوازي مع الكفرات: توزيعات الأعراس والمواليد بالليزر.
- `laser/السوق_المحلي_للحفر.md` و`laser/توريد_الكفرات.md` و`.html`: بحث السوق والتوريد.
- `samples/`: ملفات SVG لعيّنات التوزيعات (بطاقة مقوّسة، ميدالية حرف، غطاء برطمان) وصفحتها `samples/index.html`، وعيّنات كفرات الجلد في `samples/جلد.html`. المولّدان `build_samples.py` و`build_leather.py`، واعتمادياتهما في `samples/requirements.txt`.

الملفات المولَّدة وسكربتها (`laser/*.docx` و`laser/*.pdf` و`build/`) تحمل أسماء أشخاص، فهي متجاهَلة في git وتبقى محلية.
