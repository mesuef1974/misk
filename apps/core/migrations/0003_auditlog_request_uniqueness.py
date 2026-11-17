"""قيد تفرّد شرطي على مفتاح idempotency في سجل التدقيق. منفصل عن 0002: بياناتها تُثبَّت قبل بناء الفهرس."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_auditlog_actor_name")]

    operations = [
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.UniqueConstraint(
                condition=models.Q(("request_id", ""), _negated=True),
                fields=("action", "target", "request_id"),
                name="uniq_audit_action_target_request",
            ),
        ),
    ]
