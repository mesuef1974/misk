"""قراءة عدّادات المتجر لمؤشرات خطة النمو."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from apps.designs import selectors as design_selectors

from .models import StoreEventCount
from .services import design_subject

# عتبة «التصميم الغالي» في المؤشر I8.k1 (docs/growth-plan.json)، بالريال.
HIGH_PRICE = Decimal("300")


def totals(
    start: date, end: date, *, subject_prefix: str = "", subjects: Collection[str] | None = None
) -> dict[str, int]:
    """مجموع كل حدث في الفترة (الطرفان داخلان). `subject_prefix` يحصر الموضوع: «design:» للتصاميم الجاهزة،
    و`subjects` يحصره في قائمة بعينها (الفارغة لا تطابق شيئًا)."""
    rows = StoreEventCount.objects.filter(day__gte=start, day__lte=end)
    if subject_prefix:
        rows = rows.filter(subject__startswith=subject_prefix)
    if subjects is not None:
        rows = rows.filter(subject__in=subjects)
    found = dict(rows.values_list("kind").annotate(total=Sum("count")))
    return {kind: found.get(kind, 0) for kind in StoreEventCount.Kind.values}


def rate(numerator: int, denominator: int) -> float | None:
    """نسبة مئوية بمنزلة عشرية؛ None حين لا مقام: «لا بيانات» غير «صفر»."""
    return round(100 * numerator / denominator, 1) if denominator else None


def _cart_rate(start: date, end: date, slugs: Collection[str]) -> float | None:
    found = totals(start, end, subjects=[design_subject(slug) for slug in slugs])
    return rate(found[StoreEventCount.Kind.CART_ADD], found[StoreEventCount.Kind.VIEW])


def plan_metrics(start: date, end: date) -> dict[str, float]:
    """مؤشرات خطة النمو المحسوبة من القاعدة: `{معرّف المؤشر: قيمة}` بصيغة `automation/plan.py ingest`.

    المؤشر الذي لا مقام له يسقط ولا يُكتب صفرًا: «لا بيانات» لا تمحو آخر قياس في الخطة.
    التصنيف بحال المتجر الآن لا يوم الحدث: العدّاد يحمل الاسم وحده، فتصميم تغيّر سعره يُحسب بفئته الحالية.
    """
    offered = complete = 0
    personalized: list[str] = []
    high_priced: list[str] = []
    for design in design_selectors.listed_designs():
        slug = design.slug or ""  # المنشور له اسم دائمًا (`listed_designs`)
        prices: list[Decimal] = []
        for variant in design.variants.all():
            rows = design_selectors.offers(variant)
            if not rows:
                continue
            offered += 1
            complete += all(row.complete for row in rows)
            prices.extend(row.price for row in rows if row.price is not None)
        if design.personalization:
            personalized.append(slug)
        # «السعر» ما يراه الزائر على البطاقة: أدنى عرض للتصميم.
        if prices and min(prices) > HIGH_PRICE:
            high_priced.append(slug)
    found = {
        "C0.k1": rate(complete, offered),
        "I1.k1": _cart_rate(start, end, personalized),
        "I8.k1": _cart_rate(start, end, high_priced),
    }
    return {kpi: value for kpi, value in found.items() if value is not None}
