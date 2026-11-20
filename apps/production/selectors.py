"""قراءة الإنتاج."""

from __future__ import annotations

from django.db.models import Count, QuerySet, Sum

from apps.orders.models import OrderItem

from .models import Placement, Sheet


def sheets(status: str | None = None) -> QuerySet[Sheet]:
    """الألواح بقطعها (مع طلب كل قطعة وقالبها) وسجل تشغيلها، بعدد استعلامات ثابت."""
    queryset = Sheet.objects.select_related("material").prefetch_related(
        "placements__order_item__order__customer", "placements__order_item__template", "runs"
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def waiting_sheets(material_id: int) -> int:
    """ألواح المادة المخطَّطة التي لم تُقصّ بعد: تخطيط لا ينشئ جديدًا يذكرها كي لا يُفهم أن لا قطع للمادة."""
    return Sheet.objects.filter(material_id=material_id, status=Sheet.Status.PLANNED).count()


def status_counts() -> dict[str, int]:
    return dict(Sheet.objects.order_by().values_list("status").annotate(Count("id")))


def uncut_pieces(order_id: int) -> int:
    """قطع الطلب التي لم تُقصّ بعد: الكمية المطلوبة ناقص القطع الموضوعة على ألواح منفَّذة."""
    wanted = OrderItem.objects.filter(order_id=order_id).aggregate(total=Sum("quantity"))["total"] or 0
    cut = Placement.objects.filter(order_item__order_id=order_id, sheet__status=Sheet.Status.DONE).count()
    return max(wanted - cut, 0)
