"""حقن مواد الكتالوج وقوالبه من ملف JSON. idempotent: إعادة التشغيل تحدّث الصف نفسه ولا تضاعفه."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog import services
from apps.catalog.domain import ParamError

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "seed" / "catalog.json"
MATERIAL_DECIMALS = ("sheet_width_mm", "sheet_height_mm", "sheet_cost")
TEMPLATE_DECIMALS = ("width_mm", "height_mm", "safe_margin_mm", "base_price")


class Command(BaseCommand):
    help = (
        "يحقن المواد والقوالب من ملف JSON عبر خدمات الكتالوج (المفتاح: الاسم والسماكة للمادة، وslug للقالب)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", type=Path, default=DEFAULT_FILE, help="ملف البيانات (افتراضيًّا seed/catalog.json)"
        )
        parser.add_argument("--dry-run", action="store_true", help="يتحقق من الملف كله ثم يتراجع بلا كتابة")

    def handle(self, *args, **options):
        try:
            data = json.loads(options["file"].read_text(encoding="utf-8"))
            materials, templates = data["materials"], data["templates"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(f"ملف البيانات غير صالح: {error}") from error

        try:
            with transaction.atomic():
                for row in materials:
                    fields = {**row, **{key: Decimal(row[key]) for key in MATERIAL_DECIMALS if key in row}}
                    services.upsert_material(
                        name=fields.pop("name"),
                        kind=fields.pop("kind"),
                        thickness_mm=Decimal(fields.pop("thickness_mm")),
                        **fields,
                    )
                for row in templates:
                    fields = {**row, **{key: Decimal(row[key]) for key in TEMPLATE_DECIMALS if key in row}}
                    services.upsert_template(
                        slug=fields.pop("slug"), param_schema=fields.pop("param_schema"), **fields
                    )
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except (ParamError, ValidationError, ArithmeticError, KeyError, TypeError, ValueError) as error:
            raise CommandError(f"تعذّر الحقن ولم يُكتب شيء: {error}") from error

        verb = "صالحة ولم تُكتب" if options["dry_run"] else "حُقنت"
        self.stdout.write(f"{verb}: {len(materials)} مواد و{len(templates)} قوالب")
