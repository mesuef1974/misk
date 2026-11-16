"""مسارات الطلبات."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.auth import staff_auth

from . import selectors, services
from .models import Order

router = Router(tags=["الطلبات"], auth=staff_auth)


class ItemIn(Schema):
    template_slug: str
    material_id: int
    params: dict[str, Any] = {}
    quantity: int = 1
    unit_price: Decimal | None = None


class OrderIn(Schema):
    client_ref: uuid.UUID
    customer_name: str
    items: list[ItemIn]
    occasion_date: date | None = None
    notes: str = ""


class TransitionIn(Schema):
    to_status: str


class ItemOut(Schema):
    id: int
    template_slug: str
    material_id: int
    params: dict[str, Any]
    quantity: int
    unit_price: Decimal

    @staticmethod
    def resolve_template_slug(obj) -> str:
        return obj.template.slug


class OrderOut(Schema):
    id: int
    client_ref: uuid.UUID
    customer_name: str
    status: str
    occasion_date: date | None
    notes: str
    total: Decimal
    items: list[ItemOut]

    @staticmethod
    def resolve_customer_name(obj) -> str:
        return obj.customer.name


@router.get("", response=list[OrderOut])
def list_orders(request: HttpRequest, status: str | None = None):
    return selectors.orders(status)


@router.post("", response=OrderOut)
def create_order(request: HttpRequest, payload: OrderIn):
    try:
        order = services.create_order(
            client_ref=payload.client_ref,
            customer_name=payload.customer_name,
            items=[services.ItemInput(**item.dict()) for item in payload.items],
            occasion_date=payload.occasion_date,
            notes=payload.notes,
            actor=request.user,
        )
    except services.OrderError as exc:
        raise HttpError(422, str(exc)) from exc
    return selectors.order(order.pk)


@router.get("/{order_id}", response=OrderOut)
def get_order(request: HttpRequest, order_id: int):
    try:
        return selectors.order(order_id)
    except Order.DoesNotExist as exc:
        raise HttpError(404, "الطلب غير موجود") from exc


@router.post("/{order_id}/transition", response=OrderOut)
def transition(request: HttpRequest, order_id: int, payload: TransitionIn):
    if payload.to_status not in Order.Status.values:
        raise HttpError(422, "حالة غير معروفة")
    try:
        services.transition(order_id=order_id, to_status=payload.to_status, actor=request.user)
    except Order.DoesNotExist as exc:
        raise HttpError(404, "الطلب غير موجود") from exc
    except services.OrderError as exc:
        raise HttpError(409, str(exc)) from exc
    return selectors.order(order_id)
