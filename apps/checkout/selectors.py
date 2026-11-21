"""قراءة السلة كما يراها العميل: بنودها ومجموعها وأقرب جاهزية ورابط الدفع إن فُتحت جلسته."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.orders.models import Order

from . import services
from .models import Payment

VISIBLE = (Order.Status.DRAFT, Order.Status.AWAITING_PAYMENT)
EMPTY: dict[str, Any] = {
    "status": "empty",
    "items": [],
    "subtotal": Decimal("0"),
    "delivery_fee": Decimal("0"),
    "total": Decimal("0"),
    "currency": services.CURRENCY,
    "ready_on": None,
    "needs_review": False,
    "payment_url": None,
}


def cart_view(order: Order | None, *, now: datetime) -> dict[str, Any]:
    """سلة دُفعت أو أُلغيت تُعرض فارغة: ما بعد الدفع يُتابَع برابط التتبّع لا بالسلة."""
    if order is None or order.status not in VISIBLE:
        return EMPTY
    items = [
        {
            "id": item.pk,
            "template_slug": item.template.slug,
            "name": item.template.name,
            "name_en": item.template.name_en,
            "material_id": item.material_id,
            "material_name": item.material.name,
            "material_name_en": item.material.name_en,
            "params": item.params,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_total": item.unit_price * item.quantity,
            "needs_review": bool(item.review_reasons),
        }
        for item in order.items.select_related("template", "material")
    ]
    subtotal = sum((row["line_total"] for row in items), Decimal("0"))
    live = None
    if order.status == Order.Status.AWAITING_PAYMENT:
        live = order.payments.filter(status=Payment.Status.PENDING, expires_at__gt=now).first()
    return {
        "status": order.status,
        "items": items,
        "subtotal": subtotal,
        "delivery_fee": order.delivery_fee,
        "total": subtotal + order.delivery_fee,
        "currency": services.CURRENCY,
        "ready_on": services.ready_on(order, now=now) if items else None,
        "needs_review": any(row["needs_review"] for row in items),
        "payment_url": live.payment_url if live else None,
    }
