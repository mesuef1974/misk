"""كتابة الكتالوج: كل عملية idempotent على مفتاحها الطبيعي وتُسجَّل في سجل التدقيق."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.core.services import record_audit

from . import domain
from .models import Calibration, Material, ProductTemplate


@transaction.atomic
def upsert_material(*, name: str, kind: str, thickness_mm: Decimal, actor=None, **fields: Any) -> Material:
    material, _ = Material.objects.update_or_create(
        name=" ".join(name.split()), thickness_mm=thickness_mm, defaults={"kind": kind, **fields}
    )
    material.full_clean()
    record_audit(action="catalog.material.upsert", actor=actor, target=f"material:{material.pk}")
    return material


@transaction.atomic
def record_calibration(
    *,
    material: Material,
    operation: str,
    power_pct: int,
    speed_mm_s: Decimal,
    min_line_mm: Decimal,
    measured_on: date,
    passes: int = 1,
    lines_per_cm: int | None = None,
    notes: str = "",
    actor=None,
) -> Calibration:
    """قياس مكرر بالقيم نفسها في اليوم نفسه يعيد السجل الموجود ولا يضاعفه."""
    lookup = {
        "material": material,
        "operation": operation,
        "power_pct": power_pct,
        "speed_mm_s": speed_mm_s,
        "passes": passes,
        "measured_on": measured_on,
    }
    existing = Calibration.objects.filter(**lookup).first()
    if existing:
        return existing
    calibration = Calibration(**lookup, lines_per_cm=lines_per_cm, min_line_mm=min_line_mm, notes=notes)
    calibration.full_clean()
    calibration.save()
    record_audit(action="catalog.calibration.record", actor=actor, target=f"calibration:{calibration.pk}")
    return calibration


@transaction.atomic
def upsert_template(
    *, slug: str, param_schema: list[dict[str, Any]], actor=None, **fields: Any
) -> ProductTemplate:
    domain.validate_schema(param_schema)
    if "material_kinds" in fields:
        domain.validate_material_kinds(fields["material_kinds"], set(Material.Kind.values))
    template, _ = ProductTemplate.objects.update_or_create(
        slug=slug, defaults={"param_schema": param_schema, **fields}
    )
    template.full_clean()
    record_audit(action="catalog.template.upsert", actor=actor, target=f"template:{template.slug}")
    return template
