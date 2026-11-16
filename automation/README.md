# طبقة الأتمتة

دورة البطاقة (16 خطوة في مخطط المشروع) مُنفَّذة هنا بثلاثة أجزاء:

1. `ledger.py` — دفتر أحداث append-only بصيغة JSONL في `automation/ledger/`. البطاقة = سلسلة أحداث
   (`created → ready → claimed → coded → prepush_ok → pr_opened → ci_green → approved → merged → deployed`).
   لا تُحرَّر الأحداث؛ تُضاف فقط. الحالة الحالية = آخر حدث.
2. `runner.py` — مشغّل مجدوَل (cron / Task Scheduler) بقفل ملفّي: يلتقط بطاقة `ready`، ينشئ `git worktree`
   في `.worktrees/<card>`، يشغّل `claude -p` بصلاحيات مخفَّضة (لا push ولا gh merge ولا railway)،
   ثم يشغّل `scripts/prepush_check.py`، ويفتح PR بنفسه (المشغّل هو من يدفع، لا النموذج)، ويسجّل كل خطوة في الدفتر.
3. `scripts/` — البوابات: `prepush_check.py` محليًا، وفي CI: `pr_approval_head_check.py` (اعتماد مربوط بالـ SHA)،
   `check_migration_collisions.py`، `deploy_window.py` (في merge_group)، و`merge_gate.py` (قرار auto-merge).

## الأوامر

```bash
python automation/ledger.py new "عنوان البطاقة" --body "وصف ما يجب فعله وما يُعدّ نجاحًا"
python automation/ledger.py ready <card_id>
python automation/ledger.py list
python automation/ledger.py show <card_id>
python automation/runner.py --once            # يلتقط بطاقة واحدة
python automation/runner.py --dry-run         # يعرض ما سيفعله دون تنفيذ
```

## قواعد التصميم (من دروس مشروع المدرسة)

- النموذج لا يرى `git push` ولا `gh pr merge` ولا `railway`: المشغّل يفعلها بعد نجاح الفحص المحلي فقط.
- النجاح الشكلي خطر: `prepush_check.py` يفشل برمز 3 إن غابت أداة بدل أن ينجح صامتًا.
- ملفات CI وlockfiles وسكربتات البوابات محظورة على الدمج الآلي (`merge_gate.ALWAYS_FORBIDDEN`) حتى لا يعدّل النموذج حارسه.
- الاعتماد البشري مرة واحدة لكل بطاقة، في وصف الطلب، مربوط برأسه؛ أي دفع لاحق يُبطله.
- الدمج عبر merge queue فقط؛ نافذة النشر تُفرض هناك.
