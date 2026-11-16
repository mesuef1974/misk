"""قراءة الكتالوج."""

from __future__ import annotations

from django.db.models import QuerySet

from .models import Calibration, Material, ProductTemplate


def active_materials() -> QuerySet[Material]:
    return Material.objects.filter(is_active=True)


def active_templates() -> QuerySet[ProductTemplate]:
    return ProductTemplate.objects.filter(is_active=True)


def calibrations_for(material_id: int) -> QuerySet[Calibration]:
    return Calibration.objects.filter(material_id=material_id)


def calibrated_material_ids(material_ids: set[int]) -> set[int]:
    """المواد التي لها معايرة واحدة على الأقل، باستعلام واحد."""
    return set(
        Calibration.objects.filter(material_id__in=material_ids)
        .values_list("material_id", flat=True)
        .distinct()
    )
