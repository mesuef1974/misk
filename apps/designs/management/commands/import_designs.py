"""استيراد مجلد تصاميم: `python manage.py import_designs <المجلد> --source "<البائع>" [--listing <الرقم>]`.

يُعاد تشغيله بأمان: النسخة المعروفة ببصمة SVG تُتخطّى. التحليل يجري هنا مباشرةً (أمر خارج مسار الطلبات)، أو يُرسل
إلى العامل بـ `--async`.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.designs import services, tasks
from apps.designs.models import DesignSource


class Command(BaseCommand):
    help = "يستورد مجلد تصاميم جاهزة ويحلّلها"

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--source", required=True, help="اسم البائع كما في «مصادر التصاميم»")
        parser.add_argument("--listing", help="رقم القائمة إن لم يكن في اسم المجلد")
        parser.add_argument("--async", dest="run_async", action="store_true", help="التحليل في عامل Celery")

    def handle(self, *args, folder, source, listing, run_async, **options):
        root = Path(folder)
        if not root.is_dir():
            raise CommandError(f"ليس مجلدًا: {root}")
        try:
            design_source = DesignSource.objects.get(name=source)
        except DesignSource.DoesNotExist as exc:
            raise CommandError(f"مصدر غير معرَّف: «{source}». عرّفه ومفتاح ألوانه في لوحة الإدارة أولًا") from exc
        try:
            report = services.import_folder(root=root, source=design_source, listing=listing)
        except services.DesignError as exc:
            raise CommandError(str(exc)) from exc

        for variant in report.created:
            if run_async:
                tasks.analyze_variant_async.delay(variant.pk)
                self.stdout.write(f"استُورد {variant} وأُرسل للتحليل")
                continue
            services.analyze_variant(variant)
            state = f"خطأ: {variant.analysis_error}" if variant.analysis_error else "حُلِّل"
            self.stdout.write(f"استُورد {variant}: {state}")
        for note in report.skipped:
            self.stdout.write(self.style.WARNING(f"تُخطّي {note}"))
