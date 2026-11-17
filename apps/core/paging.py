"""ترقيم صفحات القوائم: limit/offset بحدّ أعلى، كي لا يجلب طلب واحد الجدول كله."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from ninja import Field, Schema

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class PageQuery(Schema):
    limit: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(0, ge=0)


def page_of(
    queryset: QuerySet, page: PageQuery, counts: dict[str, int], status: str | None
) -> dict[str, Any]:
    """صفحة من `queryset` المرتَّب. `counts` عدد الصفوف لكل حالة في الجدول كله، ومنه مجموع ما يطابق التصفية."""
    count = counts.get(status, 0) if status else sum(counts.values())
    return {
        "items": list(queryset[page.offset : page.offset + page.limit]),
        "count": count,
        "counts": counts,
    }
