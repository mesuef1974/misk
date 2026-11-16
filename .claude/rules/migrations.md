# الهجرات

- كل تغيير في `models.py` يرافقه `python manage.py makemigrations <app>` في الإيداع نفسه؛ `makemigrations --check` في الفحص المحلي وCI.
- Expand/Contract: أضف العمود الجديد nullable أولًا، املأه بمهمة، ثم اجعله مطلوبًا في هجرة لاحقة، ثم احذف القديم في طلب منفصل.
- لا `RunPython` يقرأ نموذجًا غير `apps.get_model`.
- قبل الدفع شغّل `python scripts/check_migration_collisions.py` إن كانت بطاقة أخرى تمسّ التطبيق نفسه.
- الهجرات محظورة على الدمج الآلي (`security/sensitive_paths.json`): تُراجَع بشريًا دائمًا.
