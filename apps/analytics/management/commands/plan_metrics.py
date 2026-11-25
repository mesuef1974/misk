"""لقطة مؤشرات خطة النمو من القاعدة، JSON على المخرج: `{معرّف المؤشر: قيمة}`.

    python manage.py plan_metrics > snapshot.json && python automation/plan.py ingest snapshot.json

المؤشر الذي لا بيانات له يغيب عن اللقطة، فلا يمسّه `ingest`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics import selectors


class Command(BaseCommand):
    help = "يطبع مؤشرات خطة النمو المحسوبة من القاعدة JSON، لفترة تنتهي بـ--date وطولها --days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=date.fromisoformat, default=None, help="آخر يوم في الفترة (افتراضه اليوم)"
        )
        parser.add_argument("--days", type=int, default=7, help="طول الفترة بالأيام (افتراضه 7)")

    def handle(self, *args, **options):
        if options["days"] < 1:
            raise CommandError("--days يجب أن يكون 1 أو أكثر")
        end = options["date"] or timezone.localdate()
        start = end - timedelta(days=options["days"] - 1)
        self.stdout.write(json.dumps(selectors.plan_metrics(start, end), sort_keys=True))
