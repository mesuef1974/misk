"""قراءة عدّادات المتجر لمؤشرات خطة النمو."""

from __future__ import annotations

from datetime import date

from django.db.models import Sum

from .models import StoreEventCount


def totals(start: date, end: date, *, subject_prefix: str = "") -> dict[str, int]:
    """مجموع كل حدث في الفترة (الطرفان داخلان). `subject_prefix` يحصر الموضوع: «design:» للتصاميم الجاهزة."""
    rows = StoreEventCount.objects.filter(day__gte=start, day__lte=end)
    if subject_prefix:
        rows = rows.filter(subject__startswith=subject_prefix)
    found = dict(rows.values_list("kind").annotate(total=Sum("count")))
    return {kind: found.get(kind, 0) for kind in StoreEventCount.Kind.values}


def rate(numerator: int, denominator: int) -> float | None:
    """نسبة مئوية بمنزلة عشرية؛ None حين لا مقام: «لا بيانات» غير «صفر»."""
    return round(100 * numerator / denominator, 1) if denominator else None
