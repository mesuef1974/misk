"""كتابة الطلبات: الإنشاء idempotent على client_ref، والحالة تتغير بانتقالات مسموحة فقط."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from apps.catalog import domain as catalog_domain
from apps.catalog import selectors as catalog_selectors
from apps.catalog.models import Material
from apps.core.columns import column_length
from apps.core.services import record_audit

from . import signals
from .models import Customer, Order, OrderItem

Status = Order.Status

Channel = Order.Channel
CURRENCY = "QAR"

TRANSITIONS: dict[str, set[str]] = {
    Status.DRAFT: {Status.CONFIRMED, Status.AWAITING_PAYMENT, Status.CANCELLED},
    Status.AWAITING_PAYMENT: {Status.PAID, Status.CANCELLED},
    Status.PAID: {Status.UNDER_REVIEW, Status.CONFIRMED},
    Status.UNDER_REVIEW: {Status.CONFIRMED, Status.CANCELLED},
    Status.CONFIRMED: {Status.IN_PRODUCTION, Status.CANCELLED},
    Status.IN_PRODUCTION: {Status.READY, Status.CANCELLED},
    Status.READY: {Status.DELIVERED, Status.OUT_FOR_DELIVERY, Status.READY_FOR_PICKUP},
    Status.OUT_FOR_DELIVERY: {Status.DELIVERED},
    Status.READY_FOR_PICKUP: {Status.DELIVERED},
    Status.DELIVERED: {Status.REFUNDED},
    Status.CANCELLED: {Status.REFUNDED},
    Status.REFUNDED: set(),
}

# حالات يدخلها النظام وحده (خدمة الدفع وإشعار البوابة)، لا زر في لوحة الطاقم.
SYSTEM_ONLY: frozenset[str] = frozenset({Status.AWAITING_PAYMENT, Status.PAID, Status.REFUNDED})
# طلب المتجر لا يُؤكَّد من المسودة: طريقه الدفع. وطلب الطاقم لا دفع له عبر البوابة.
_STAFF_ONLY_EDGES = {(Status.DRAFT, Status.CONFIRMED)}
_STOREFRONT_ONLY_EDGES = {
    (Status.DRAFT, Status.AWAITING_PAYMENT),
    (Status.DELIVERED, Status.REFUNDED),
    (Status.CANCELLED, Status.REFUNDED),
}
_FULFILLMENT_EDGES = {
    (Status.READY, Status.OUT_FOR_DELIVERY): Order.Fulfillment.DELIVERY,
    (Status.READY, Status.READY_FOR_PICKUP): Order.Fulfillment.PICKUP,
}


def allowed_transitions(order: Order, *, system: bool = False) -> set[str]:
    """الحالات التي يصلها هذا الطلب الآن، بحسب قناته وطريقة استلامه ومن يطلب الانتقال."""
    allowed = set()
    for to_status in TRANSITIONS[order.status]:
        edge = (order.status, to_status)
        if to_status in SYSTEM_ONLY and not system:
            continue
        if edge in _STAFF_ONLY_EDGES and order.channel != Channel.STAFF:
            continue
        if edge in _STOREFRONT_ONLY_EDGES and order.channel != Channel.STOREFRONT:
            continue
        if edge in _FULFILLMENT_EDGES and order.fulfillment != _FULFILLMENT_EDGES[edge]:
            continue
        if edge == (Status.READY, Status.DELIVERED) and order.fulfillment:
            continue  # ما له طريقة استلام يمر بخطوتها أولًا
        allowed.add(to_status)
    return allowed


def new_tracking_token() -> str:
    return secrets.token_urlsafe(32)


MAX_ITEMS = 100
MAX_QUANTITY = 1000  # كل نسخة قطعة في تخطيط الألواح
MAX_NOTES_LENGTH = 2000
NAME_LENGTH = column_length(Customer, "name")
_PRICE = OrderItem._meta.get_field("unit_price")
PRICE_DIGITS, PRICE_DECIMALS = _PRICE.max_digits, _PRICE.decimal_places
MAX_PRICE = Decimal(10) ** (PRICE_DIGITS - PRICE_DECIMALS)


class OrderError(ValueError):
    """مخالفة لقاعدة عمل في الطلبات."""


@dataclass(frozen=True)
class ItemInput:
    template_slug: str
    material_id: int
    params: dict[str, Any]
    quantity: int = 1
    unit_price: Decimal | None = None


def _existing_order(client_ref: uuid.UUID) -> Order | None:
    return Order.objects.filter(client_ref=client_ref).first()


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
    """إعادة الإرسال بالـ client_ref نفسه تعيد الطلب الموجود ولا تنشئ ثانيًا، ولو تزامن الطلبان.

    الزبون يُطابَق بالاسم المنظَّف: طلبات الاسم نفسه على صف واحد (لا هاتف يميّز بعد).
    """
    existing = _existing_order(client_ref)
    if existing:
        return existing
    if not items:
        raise OrderError("الطلب يحتاج بندًا واحدًا على الأقل")
    if len(items) > MAX_ITEMS:
        raise OrderError(f"الطلب لا يزيد على {MAX_ITEMS} بند")
    name = " ".join(customer_name.split())
    if not name:
        raise OrderError("اسم العميل مطلوب")
    if len(name) > NAME_LENGTH:
        raise OrderError(f"اسم العميل أطول من {NAME_LENGTH} حرفًا")
    if len(notes) > MAX_NOTES_LENGTH:
        raise OrderError(f"الملاحظات أطول من {MAX_NOTES_LENGTH} حرف")

    templates = catalog_selectors.active_templates().in_bulk(
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
        if not 1 <= item.quantity <= MAX_QUANTITY:
            raise OrderError(f"البند {index}: الكمية بين 1 و{MAX_QUANTITY}")
        try:
            params = catalog_domain.clean_params(template.param_schema, item.params)
        except catalog_domain.ParamError as exc:
            raise OrderError(f"البند {index}: {exc}") from exc
        price = template.base_price if item.unit_price is None else item.unit_price
        if not price.is_finite() or price < 0:
            raise OrderError(f"البند {index}: السعر لا يكون سالبًا")
        if price >= MAX_PRICE or price != price.quantize(Decimal(1).scaleb(-PRICE_DECIMALS)):
            raise OrderError(f"البند {index}: السعر أقل من {MAX_PRICE} وبخانتين عشريتين على الأكثر")
        rows.append(
            OrderItem(
                template=template, material=material, params=params, quantity=item.quantity, unit_price=price
            )
        )

    try:
        with transaction.atomic():  # نقطة حفظ: فشل القيد لا يُفسد المعاملة الخارجية
            # زبون لكل طلب لا مطابقة بالاسم: الاسم لا يميّز شخصين، فالمطابقة به تنسب طلب أحدهما
            # وبياناته إلى الآخر (PDPPL)، وطلبان متزامنان بالاسم نفسه كانا ينشئان زبونين على أي حال.
            customer = Customer.objects.create(name=name)
            order = Order.objects.create(
                client_ref=client_ref,
                customer=customer,
                occasion_date=occasion_date,
                notes=notes,
                tracking_token=new_tracking_token(),
            )
    except IntegrityError:
        # طلب متزامن بالـ client_ref نفسه سبق بعد فحصنا: نعيد طلبه بدل 500.
        existing = _existing_order(client_ref)
        if existing is None:
            raise
        return existing
    for row in rows:
        row.order = order
    OrderItem.objects.bulk_create(rows)
    record_audit(
        action="orders.create", actor=actor, target=f"order:{order.pk}", payload={"items": len(rows)}
    )
    return order


@transaction.atomic
def transition(*, order_id: int, to_status: str, actor=None, system: bool = False) -> Order:
    """الانتقال إلى الحالة الحالية نفسها لا يغيّر شيئًا. التأكيد يشترط معايرة لكل مادة في الطلب.

    «جاهز» يُرسل `order_ready_requested` قبل الحفظ، وبه يرفض الإنتاج طلبًا بقيت فيه قطعة لم تُقصّ.

    الإلغاء يرسل `order_cancelled` في المعاملة نفسها، وبه يرفع الإنتاج قطع الطلب عن الألواح التي لم تُقصّ.

    `system=True` لخدمة الدفع وحدها: به تُفتح حالات `SYSTEM_ONLY`. مسار الطاقم لا يمرّره.
    """
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == to_status:
        return order
    if to_status not in allowed_transitions(order, system=system):
        raise OrderError(f"لا انتقال من «{order.get_status_display()}» إلى «{Status(to_status).label}»")
    if to_status == Status.CONFIRMED:
        material_ids = set(order.items.values_list("material_id", flat=True))
        missing = material_ids - catalog_selectors.calibrated_material_ids(material_ids)
        if missing:
            names = "، ".join(str(m) for m in Material.objects.filter(pk__in=missing))
            raise OrderError(f"لا تأكيد قبل معايرة المادة من قصاصة اختبار: {names}")
    if to_status == Status.READY:
        signals.order_ready_requested.send(sender=Order, order=order)
    previous = order.status
    order.status = to_status
    order.save(update_fields=["status", "updated_at"])
    record_audit(
        action="orders.transition",
        actor=actor,
        target=f"order:{order.pk}",
        payload={"from": previous, "to": to_status},
    )
    if to_status == Status.CANCELLED:
        # send لا send_robust: خطأ المستقبِل يُرجِع الإلغاء كله، فلا يبقى طلب ملغى وقطعه على لوح.
        signals.order_cancelled.send(sender=Order, order=order, actor=actor)
    signals.order_transitioned.send(sender=Order, order=order, previous=previous, actor=actor)
    return order
