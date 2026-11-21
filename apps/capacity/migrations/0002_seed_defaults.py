"""القيم الأولى: صف الإعداد ونوافذ التشغيل بحسب ساعات المالك (قرار 2026-11-20).

يوميًّا 14:00–22:00، والجمعة والسبت كاملين (08:00–22:00). تُعدَّل بعدها من لوحة الإدارة.
"""

from datetime import time

from django.db import migrations

FULL_DAYS = {4, 5}  # الجمعة والسبت بترقيم date.weekday()


def seed(apps, schema_editor):
    CapacityConfig = apps.get_model("capacity", "CapacityConfig")
    OperatingWindow = apps.get_model("capacity", "OperatingWindow")
    CapacityConfig.objects.get_or_create(pk=1)
    for weekday in range(7):
        OperatingWindow.objects.get_or_create(
            weekday=weekday,
            defaults={"opens": time(8 if weekday in FULL_DAYS else 14), "closes": time(22)},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("capacity", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
