"""قراءة الإنتاج."""

from __future__ import annotations

from django.db.models import QuerySet

from .models import Sheet


def sheets(status: str | None = None) -> QuerySet[Sheet]:
    queryset = Sheet.objects.select_related("material").prefetch_related("placements")
    if status:
        queryset = queryset.filter(status=status)
    return queryset
