"""كتابة الطلبات: الإنشاء idempotent على client_ref، والحالة تتغير بانتقالات مسموحة فقط."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.catalog import domain as catalog_domain
from apps.catalog import selectors as catalog_selectors
from apps.catalog.models import Material, ProductTemplate
from apps.core.services import record_audit

from .models import Customer, Order, OrderItem

Status = Order.Status

TRANSITIONS: dict[str, set[str]] = {
    Status.DRAFT: {Status.CONFIRMED, Status.CANCELLED},
    Status.CONFIRMED: {Status.IN_PRODUCTION, Status.CANCELLED},
    Status.IN_PRODUCTION: {Status.READY, Status.CANCELLED},
    Status.READY: {Status.DELIVERED},
    Status.DELIVERED: set(),
    Status.CANCELLED: set(),
}


class OrderError(ValueError):
    """مخالفة لقاعدة عمل في الطلبات."""


@dataclass(frozen=True)
class ItemInput:
    template_slug: str
    material_id: int
    params: dict[str, Any]
    quantity: int = 1
    unit_price: Decimal | None = None


@transaction.atomic
def create_order(
    *,
    client_ref: uuid.UUID,
    customer_name: str,
    items: list[ItemInput],
    occasion_date: date | None = None,
    notes: str = "",
    actor=None,
) -> Order:
    """إعادة الإرسال بالـ client_ref نفسه تعيد الطلب الموجود ولا تنشئ ثانيًا."""
    existing = Order.objects.filter(client_ref=client_ref).first()
    if existing:
        return existing
    if not items:
        raise OrderError("الطلب يحتاج بندًا واحدًا على الأقل")
    name = " ".join(customer_name.split())
    if not name:
        raise OrderError("اسم الزبون مطلوب")

    templates = ProductTemplate.objects.filter(is_active=True).in_bulk(
        {item.template_slug for item in items}, field_name="slug"
    )
    materials = Material.objects.filter(is_active=True).in_bulk({item.material_id for item in items})
    rows: list[OrderItem] = []
    for index, item in enumerate(items, start=1):
        template = templates.get(item.template_slug)
        material = materials.get(item.material_id)
        if template is None:
            raise OrderError(f"البند {index}: القالب {item.template_slug} غير موجود أو موقوف")
        if material is None:
            raise OrderError(f"البند {index}: المادة {item.material_id} غير موجودة أو موقوفة")
        if item.quantity < 1:
            raise OrderError(f"البند {index}: الكمية يجب أن تكون 1 أو أكثر")
        try:
            params = catalog_domain.clean_params(template.param_schema, item.params)
        except catalog_domain.ParamError as exc:
            raise OrderError(f"البند {index}: {exc}") from exc
        price = template.base_price if item.unit_price is None else item.unit_price
        if price < 0:
            raise OrderError(f"البند {index}: السعر لا يكون سالبًا")
        rows.append(
            OrderItem(
                template=template, material=material, params=params, quantity=item.quantity, unit_price=price
            )
        )

    customer = Customer.objects.create(name=name)
    order = Order.objects.create(
        client_ref=client_ref, customer=customer, occasion_date=occasion_date, notes=notes
    )
    for row in rows:
        row.order = order
    OrderItem.objects.bulk_create(rows)
    record_audit(
        action="orders.create", actor=actor, target=f"order:{order.pk}", payload={"items": len(rows)}
    )
    return order


@transaction.atomic
def transition(*, order_id: int, to_status: str, actor=None) -> Order:
    """الانتقال إلى الحالة الحالية نفسها لا يغيّر شيئًا. التأكيد يشترط معايرة لكل مادة في الطلب."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == to_status:
        return order
    if to_status not in TRANSITIONS[order.status]:
        raise OrderError(f"لا انتقال من «{order.get_status_display()}» إلى «{Status(to_status).label}»")
    if to_status == Status.CONFIRMED:
        material_ids = set(order.items.values_list("material_id", flat=True))
        missing = material_ids - catalog_selectors.calibrated_material_ids(material_ids)
        if missing:
            names = "، ".join(str(m) for m in Material.objects.filter(pk__in=missing))
            raise OrderError(f"لا تأكيد قبل معايرة المادة من قصاصة اختبار: {names}")
    previous = order.status
    order.status = to_status
    order.save(update_fields=["status", "updated_at"])
    record_audit(
        action="orders.transition",
        actor=actor,
        target=f"order:{order.pk}",
        payload={"from": previous, "to": to_status},
    )
    return order
