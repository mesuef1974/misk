"""قراءة فهرس التصاميم: إعداد التسعير، وما يُعرض في المتجر، وما يمنع نشر تصميم."""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Prefetch, QuerySet

from . import pricing
from .models import Design, DesignImage, DesignPricing, DesignSource, DesignVariant, VariantEstimate


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
