"""قراءة فهرس التصاميم: إعداد التسعير، وما يُعرض في المتجر، وما يمنع نشر تصميم."""

from __future__ import annotations

from decimal import Decimal
from pathlib import PurePosixPath

from django.conf import settings
from django.db.models import Exists, OuterRef, Prefetch, QuerySet

from apps.catalog import domain as catalog_domain
from apps.catalog.models import Material

from . import pricing
from .models import (
    Design,
    DesignFile,
    DesignImage,
    DesignPricing,
    DesignSource,
    DesignVariant,
    VariantEstimate,
)


def rates() -> pricing.Rates | None:
    row = DesignPricing.objects.filter(pk=1).first()
    if row is None:
        return None
    return pricing.Rates(minute_rate=row.minute_rate, margin_pct=row.margin_pct, round_to=row.round_to)


def material_kinds(variant: DesignVariant) -> set[str]:
    return {group["material"] for group in variant.analysis.get("operations", {}).values()}


def is_sellable(variant: DesignVariant) -> bool:
    """محلَّلة بلا خطأ وعملياتها على نوع مادة واحد: بند الطلب يحمل مادة واحدة."""
    return (
        variant.analyzed_at is not None and not variant.analysis_error and len(material_kinds(variant)) == 1
    )


def piece_sizes(variant: DesignVariant) -> list[tuple[Decimal, Decimal]]:
    """ما يُرصَّف لنسخة واحدة: لوح لكل جزء بمقاسه، أو لوح النسخة إن كانت ملفًّا واحدًا. بمقاس البيع."""
    parts = variant.analysis.get("parts") or []
    if parts:
        return [(Decimal(str(part["width_mm"])), Decimal(str(part["height_mm"]))) for part in parts]
    return [(variant.sheet_width_mm or Decimal("0"), variant.sheet_height_mm or Decimal("0"))]


def fits_material(variant: DesignVariant, material: Material) -> bool:
    """كل أجزاء النسخة يسعها لوح المادة بعد هامش الترصيف."""
    return all(
        catalog_domain.fits_sheet(width, height, material.sheet_width_mm, material.sheet_height_mm)
        for width, height in piece_sizes(variant)
    )


def ready_cut_name(original_name: str) -> str:
    return f"{PurePosixPath(original_name).stem}-ready.svg"


def cut_file_urls(variant: DesignVariant) -> list[str]:
    """روابط ملفات القص الجاهزة بترتيب `piece_sizes`، تحت `/media/` (للمشرفين وحدهم). الفارغ: لا ملف للجزء."""
    ready = {
        row.name: f"{settings.MEDIA_URL}{row.file.name}"
        for row in variant.files.all()
        if row.role == DesignFile.Role.READY_CUT and row.file
    }
    parts = variant.analysis.get("parts") or []
    if not parts:
        return list(ready.values())[:1] or [""]
    return [ready.get(ready_cut_name(part["name"])[:255], "") for part in parts]


def _offers() -> QuerySet[VariantEstimate]:
    return (
        VariantEstimate.objects.filter(price__isnull=False, material__is_active=True)
        .select_related("material")
        .order_by("price", "material__name")
    )


def offers(variant: DesignVariant) -> list[VariantEstimate]:
    """تقديرات النسخة المعروضة للبيع، من المحمَّل مسبقًا إن وُجد."""
    if not is_sellable(variant):
        return []
    cached = getattr(variant, "offer_rows", None)
    return list(_offers().filter(variant=variant)) if cached is None else cached


def listed_designs() -> QuerySet[Design]:
    """ما يراه الزائر: منشور ومعتمد ومصدره بترخيص تجاري وله سعر. سحب الترخيص يُسقطه هنا بلا إلغاء نشر."""
    priced = VariantEstimate.objects.filter(
        variant__design=OuterRef("pk"), price__isnull=False, material__is_active=True
    )
    return (
        Design.objects.filter(
            is_listed=True,
            slug__isnull=False,
            status=Design.Status.APPROVED,
            source__license_kind=DesignSource.License.COMMERCIAL,
        )
        .filter(Exists(priced))
        .prefetch_related(
            Prefetch("images", queryset=DesignImage.objects.order_by("sort", "id")),
            Prefetch(
                "variants",
                queryset=DesignVariant.objects.order_by("code", "id").prefetch_related(
                    Prefetch("estimates", queryset=_offers(), to_attr="offer_rows")
                ),
            ),
        )
        .order_by("name_ar", "id")
    )


def _offer_in(design: Design | None, variant_of, material_id: int):
    if design is None:
        return None
    for variant in design.variants.all():
        if variant_of(variant):
            row = next((row for row in offers(variant) if row.material_id == material_id), None)
            return (design, variant, row) if row else None
    return None


def offer(slug: str, code: str, material_id: int) -> tuple[Design, DesignVariant, VariantEstimate] | None:
    """عرض نسخة منشورة على مادة كما يراه الزائر الآن. `None`: التصميم أو النسخة أو سعرها غير معروض."""
    design = listed_designs().filter(slug=slug).first()
    return _offer_in(design, lambda variant: variant.code == code, material_id)


def current_price(variant_id: int, material_id: int) -> Decimal | None:
    """سعر النسخة على المادة إن كان تصميمها ما زال منشورًا ومعروضًا عليها."""
    design = listed_designs().filter(variants=variant_id).first()
    found = _offer_in(design, lambda variant: variant.pk == variant_id, material_id)
    return found[2].price if found else None


def listing_blockers(design: Design) -> list[str]:
    """ما ينقص التصميم ليُنشر، بنصّ يقرؤه المالك في لوحة الإدارة. فارغة: يُنشر."""
    missing: list[str] = []
    if design.status != Design.Status.APPROVED:
        missing.append("غير معتمد")
    if design.source.license_kind != DesignSource.License.COMMERCIAL:
        missing.append("ترخيص المصدر ليس تجاريًّا")
    if not design.name_ar:
        missing.append("الاسم العربي")
    if not design.name_en:
        missing.append("الاسم الإنجليزي")
    if not design.images.exists():
        missing.append("صورة عرض")
    if rates() is None:
        missing.append("إعداد التسعير")
    elif not any(offers(variant) for variant in design.variants.all()):
        missing.append("نسخة بسعر على مادة واحدة")
    return missing
