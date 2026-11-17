"""لقطة اسم الفاعل في سجل التدقيق، وتهيئة الصفوف القائمة لقيد التفرّد في الهجرة التالية."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations, models
from django.db.models import Count, Min, OuterRef, Subquery


def fill_names_and_release_duplicates(apps, schema_editor):
    AuditLog = apps.get_model("core", "AuditLog")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    # اسم الحقل وحده من النموذج الحيّ (النموذج التاريخي لا يحمل USERNAME_FIELD)؛ القراءة من apps.get_model.
    username = User.objects.filter(pk=OuterRef("actor_id")).values(get_user_model().USERNAME_FIELD)[:1]
    AuditLog.objects.filter(actor__isnull=False, actor_name="").update(actor_name=Subquery(username))
    # صفوف مكرَّرة بالمفتاح نفسه (من سباق سابق): يبقى المفتاح للأقدم ويُفرَّغ في الباقي. لا يُحذف صف تدقيق.
    duplicated = (
        AuditLog.objects.exclude(request_id="")
        .order_by()
        .values("action", "target", "request_id")
        .annotate(rows=Count("id"), first=Min("id"))
        .filter(rows__gt=1)
    )
    for group in duplicated:
        AuditLog.objects.filter(
            action=group["action"], target=group["target"], request_id=group["request_id"]
        ).exclude(pk=group["first"]).update(request_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="actor_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.RunPython(fill_names_and_release_duplicates, migrations.RunPython.noop),
    ]
