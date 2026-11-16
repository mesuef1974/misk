"""قراءة الطلبات: المجموع يُحسب في قاعدة البيانات، والبنود تُجلب مسبقًا لتجنّب N+1."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, QuerySet, Sum
from django.db.models.functions import Coalesce

from .models import Order

_LINE_TOTAL = ExpressionWrapper(
    F("items__quantity") * F("items__unit_price"), output_field=DecimalField(max_digits=12, decimal_places=2)
)


def orders(status: str | None = None) -> QuerySet[Order]:
    queryset = (
        Order.objects.select_related("customer")
        .prefetch_related("items__template", "items__material")
        .annotate(total=Coalesce(Sum(_LINE_TOTAL), Decimal("0")))
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def order(order_id: int) -> Order:
    return orders().get(pk=order_id)
