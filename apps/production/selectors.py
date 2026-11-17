"""قراءة الإنتاج."""

from __future__ import annotations

from django.db.models import Count, QuerySet

from .models import Sheet


def sheets(status: str | None = None) -> QuerySet[Sheet]:
    """الألواح بقطعها (مع طلب كل قطعة وقالبها) وسجل تشغيلها، بعدد استعلامات ثابت."""
    queryset = Sheet.objects.select_related("material").prefetch_related(
        "placements__order_item__order__customer", "placements__order_item__template", "runs"
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def status_counts() -> dict[str, int]:
    return dict(Sheet.objects.order_by().values_list("status").annotate(Count("id")))
