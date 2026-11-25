# طبقة الأتمتة

دورة البطاقة (16 خطوة في مخطط المشروع) مُنفَّذة هنا بثلاثة أجزاء:

1. `ledger.py` — دفتر أحداث append-only بصيغة JSONL في `automation/ledger/`. البطاقة = سلسلة أحداث
   (`created → ready → claimed → coded → prepush_ok → pr_opened → ci_green → approved → merged → deployed`).
   لا تُحرَّر الأحداث؛ تُضاف فقط. الحالة الحالية = آخر حدث.
2. `runner.py` — مشغّل مجدوَل (cron / Task Scheduler) بقفل ملفّي: يلتقط بطاقة `ready`، ينشئ `git worktree`
   في `.worktrees/<card>`، يشغّل `claude -p` بصلاحيات مخفَّضة (لا push ولا gh merge ولا railway)،
   ثم يشغّل `scripts/prepush_check.py`، ويفتح PR بنفسه (المشغّل هو من يدفع، لا النموذج)، ويسجّل كل خطوة في الدفتر.
3. `scripts/` — البوابات: `prepush_check.py` محليًا، وفي CI: `pr_approval_head_check.py` (اعتماد مربوط بالـ SHA)،
   `check_migration_collisions.py`، و`merge_gate.py` (قرار auto-merge).

## الأوامر

```bash
python automation/ledger.py new "عنوان البطاقة" --body "وصف ما يجب فعله وما يُعدّ نجاحًا"
python automation/ledger.py ready <card_id>
python automation/ledger.py list
python automation/ledger.py show <card_id>
python automation/runner.py --once            # يلتقط بطاقة واحدة
python automation/runner.py --dry-run         # يعرض ما سيفعله دون تنفيذ
python automation/runner.py --approve-baseline # المالك وحده: يطبع إعداد git وخطّافاته ويعتمده ويرفع الإيقاف
python automation/plan.py render              # يولّد docs/growth-plan.md من docs/growth-plan.json
python automation/plan.py check               # يفشل إن كان التقرير قديمًا أو الخطة غير صالحة
python automation/plan.py kpi I1.k2 32        # قيمة مؤشر؛ --field baseline|target للأساس والهدف
python automation/plan.py ingest snapshot.json # لقطة {معرّف المؤشر: قيمة} من أمر القياس
```

خطة النمو (`plan.py`): الخطة بيانات في `docs/growth-plan.json`، والتقرير مولَّد منها. خطوة لها `card` تأخذ حالتها من
الدفتر (`merged`/`deployed` = تمت) فتتحدّث بلا تحرير. `tests/test_plan.py` يفشل إن عُدِّلت الخطة ولم يُولَّد التقرير.

قبل أول تشغيل يعتمد المالك بصمة إعداد git (`--approve-baseline`)، وتُحفظ خارج المستودع في `MISK_RUNNER_STATE`
(افتراضًا `~/.misk-runner`). أي تغيّر عنها، أو في أثناء تشغيل بطاقة، يكتب ملف `halt` هناك فيقف المشغّل حتى يراجع المالك
الإعداد ويعتمده من جديد. أسطر التتبّع `branch.<x>.remote/merge` التي يكتبها `git push -u` لا توقفه.

## عزل الرموز وحدوده

النموذج والفحص ينفّذان شيفرة البطاقة في بيئة بلا متغيرات رموز، وبإعداد gh فارغ (`GH_CONFIG_DIR`)، وبلا مساعد اعتماد git،
والفحص بمنزل مؤقت. هذا يمنع الوصول العَرَضي لا المتعمَّد: البيئة متغيرات تستطيع العملية تغييرها، وما يحفظه حساب Windows
خارجها يبقى في متناولها. رمز `gh` محفوظ في keyring (مدير اعتمادات Windows) لا في ملف، فيصله `gh` بعد حذف
`GH_CONFIG_DIR`، ويصل اعتماد git باستدعاء git-credential-manager مباشرةً، وخطوة النموذج ترى المنزل الحقيقي بمفاتيح SSH
وإعداد railway.

الحل التشغيلي: شغّل المشغّل المجدوَل من حساب Windows مستقل لا يحفظ اعتماد GitHub ولا مفاتيح SSH ولا إعداد railway،
وأعطه الرمز في `GH_TOKEN` ضمن بيئة المهمة المجدوَلة وحدها (يُحذف من بيئة النموذج والفحص). وحتى ذلك يسأل المشغّل في
بدايته `gh` وgit عن اعتماد محفوظ، فإن وجده طبع تحذيرًا وسجّل مصدره في `exposed_credentials` بحدث `claimed`، ثم يكمل.

## قواعد التصميم (من دروس مشروع المدرسة)

- النموذج لا يرى `git push` ولا `gh pr merge` ولا `railway`: المشغّل يفعلها بعد نجاح الفحص المحلي فقط.
- النجاح الشكلي خطر: `prepush_check.py` يفشل برمز 3 إن غابت أداة بدل أن ينجح صامتًا.
- ملفات CI وlockfiles وسكربتات البوابات محظورة على الدمج الآلي (`merge_gate.ALWAYS_FORBIDDEN`) حتى لا يعدّل النموذج حارسه.
- الاعتماد البشري مرة واحدة لكل بطاقة، في وصف الطلب، مربوط برأسه؛ أي دفع لاحق يُبطله. الفحص لا يتحقق من كاتب السطر
  (الجلسة والمالك حساب واحد على GitHub)، فالضابط إجرائي: الجلسة لا تكتبه إلا بأمر المالك الصريح لكل رأس.
- البوابات تفشل مغلقة: حالة CI غير معروفة، أو غياب `sensitive_paths.json`، أو تعذّر حصر الملفات، كلها منع لا نجاح.
- `merge_gate.py --enable` يربط الدمج الآلي بالرأس المقيس (`--match-head-commit`)، ويقرأ الاسم القديم والجديد للملف المعاد تسميته.
- المشغّل لا يدفع إلا رأسًا مفحوصًا بشجرة نظيفة وإيداعات فوق main، وقفله إنشاء حصري.
- لا نافذة نشر: الدمج إلى `main` مسموح في أي وقت (قرار المالك 2026-11-18).
