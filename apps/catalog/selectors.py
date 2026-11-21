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


def template_by_slug(slug: str) -> ProductTemplate | None:
    return ProductTemplate.objects.filter(slug=slug, is_active=True).first()


def engrave_calibration(material_id: int) -> Calibration | None:
    """أحدث معايرة حفر للخامة: منها أصغر خط مقروء يحدّ مقاس النص."""
    return (
        Calibration.objects.filter(material_id=material_id, operation=Calibration.Operation.ENGRAVE)
        .order_by("-measured_on", "-id")
        .first()
    )


def storefront_materials(template: ProductTemplate) -> QuerySet[Material]:
    """خامات تُعرض للعميل على القالب: فعّالة، من أنواعه، ولها معايرة حفر (بلاها لا حدّ للنص)."""
    materials = Material.objects.filter(
        is_active=True, calibrations__operation=Calibration.Operation.ENGRAVE
    ).distinct()
    return materials.filter(kind__in=template.material_kinds) if template.material_kinds else materials


def religious_templates() -> QuerySet[ProductTemplate]:
    return ProductTemplate.objects.filter(is_active=True, allows_religious_text=True)
