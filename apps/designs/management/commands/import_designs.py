"""استيراد تصاميم: `python manage.py import_designs <مجلد أو zip> --source "<البائع>" [خيارات]`.

يُعاد تشغيله بأمان: النسخة المعروفة ببصمة SVG تُتخطّى. التحليل يجري هنا مباشرةً (أمر خارج مسار الطلبات)، أو يُرسل
إلى العامل بـ `--async`. `--scan` يعرض الخطة بلا كتابة.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.designs import scan, services, tasks
from apps.designs.models import DesignSource


class Command(BaseCommand):
    help = "يستورد مجلد تصاميم جاهزة أو أرشيفًا ويحلّلها"

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--source", required=True, help="اسم البائع كما في «مصادر التصاميم»")
        parser.add_argument("--listing", help="رقم القائمة إن لم يكن في اسم المجلد")
        parser.add_argument(
            "--tree",
            action="store_true",
            help="المجلد الأول فئة، وملف SVG مفرد في الجذر أو الفئة تصميم مستقل",
        )
        parser.add_argument(
            "--each-svg",
            action="append",
            default=[],
            metavar="PATH",
            help="مجلد أو أرشيف كل SVG فيه نسخة مستقلة لا جزء (يتكرر)",
        )
        parser.add_argument(
            "--create-source",
            action="store_true",
            help="ينشئ المصدر إن لم يوجد بترخيص «غير محدد» ومفتاح المفرد: الملف أحادي اللون قص على الخشب",
        )
        parser.add_argument("--scan", dest="show_plan", action="store_true", help="يعرض الخطة ولا يكتب شيئًا")
        parser.add_argument("--async", dest="run_async", action="store_true", help="التحليل في عامل Celery")

    def handle(
        self, *args, folder, source, listing, tree, each_svg, create_source, show_plan, run_async, **options
    ):
        root = Path(folder)
        if not root.exists():
            raise CommandError(f"غير موجود: {root}")
        if show_plan:
            self._show_plan(root, tree=tree, each_svg=each_svg, listing=listing)
            return
        if create_source:
            design_source = services.ensure_source(source)
        else:
            try:
                design_source = DesignSource.objects.get(name=source)
            except DesignSource.DoesNotExist as exc:
                raise CommandError(
                    f"مصدر غير معرَّف: «{source}». عرّفه ومفتاح ألوانه في لوحة الإدارة، أو مرّر --create-source"
                ) from exc
        try:
            report = services.import_folder(
                root=root, source=design_source, listing=listing, tree=tree, each_svg=each_svg
            )
        except services.DesignError as exc:
            raise CommandError(str(exc)) from exc

        for variant in report.created:
            if run_async:
                tasks.analyze_variant_async.delay(variant.pk)
                self.stdout.write(f"استُورد {variant} وأُرسل للتحليل")
                continue
            services.analyze_variant(variant)
            state = f"خطأ: {variant.analysis_error}" if variant.analysis_error else "حُلِّل"
            if variant.analysis.get("assumed"):
                state += " (افتراض المفرد)"
            self.stdout.write(f"استُورد {variant}: {state}")
        for note in report.skipped:
            self.stdout.write(self.style.WARNING(f"تُخطّي {note}"))
        for note in report.notes:
            self.stdout.write(self.style.NOTICE(note))
        self.stdout.write(f"المجموع: {len(report.created)} مستوردة، {len(report.skipped)} متخطّاة")

    def _show_plan(self, root: Path, *, tree, each_svg, listing) -> None:
        try:
            result = scan.scan(root)
        except scan.ScanError as exc:
            raise CommandError(str(exc)) from exc
        plans = scan.plan(result, tree=tree, each_svg=each_svg, listing=listing)
        for item in plans:
            code = f" ({item.code})" if item.code else ""
            category = f"[{item.category}] " if item.category else ""
            parts = "، ".join(e.name for e in item.parts)
            self.stdout.write(f"{category}{item.name}{code}: {len(item.parts)} جزء: {parts}")
        for note in result.notes:
            self.stdout.write(self.style.NOTICE(note))
        self.stdout.write(f"المجموع: {len(plans)} نسخة")
