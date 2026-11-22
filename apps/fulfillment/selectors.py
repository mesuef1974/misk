"""قراءة الاستلام والتوصيل: الإعداد، المناطق، المواعيد الحرة، والطلب كما يراه صاحبه برابط التتبّع."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.capacity import selectors as capacity_selectors
from apps.core.columns import column_length
from apps.core.models import AuditLog
from apps.orders import services as orders_services
from apps.orders.models import Order

from . import domain
from .models import Delivery, DeliveryZone, FulfillmentConfig, PickupAppointment

Status = Order.Status
# الحجز مفتوح ما دام الطلب جاهزًا ولم يُسلَّم؛ بعد الحجز يبقى تغيير الموعد متاحًا.
BOOKABLE = (Status.READY, Status.READY_FOR_PICKUP)
TOKEN_LENGTH = column_length(Order, "tracking_token")


def config() -> FulfillmentConfig:
    return FulfillmentConfig.objects.filter(pk=1).first() or FulfillmentConfig(pk=1)


def active_zones() -> QuerySet[DeliveryZone]:
    return DeliveryZone.objects.filter(is_active=True)


def active_zone(zone_id: int | None) -> DeliveryZone | None:
    if zone_id is None:
        return None
    return active_zones().filter(pk=zone_id).first()


def tracked_order(token: str) -> Order | None:
    """الطلب صاحب الرابط. السلة التي لم تبلغ الدفع ليست طلبًا يُتابَع."""
    if not token or len(token) > TOKEN_LENGTH:
        return None
    return Order.objects.filter(tracking_token=token).exclude(status=Status.DRAFT).first()


def can_book_pickup(order: Order) -> bool:
    return order.fulfillment == Order.Fulfillment.PICKUP and order.status in BOOKABLE


def free_slots(*, now: datetime) -> list[tuple[date, list[datetime]]]:
    """المواعيد الحرة لكل يوم حضور في أفق الحجز، بعد مهلة الإعداد وعدا المحجوز. يوم بلا موعد لا يظهر."""
    cfg = config()
    local = timezone.localtime(now)
    earliest = local + timedelta(minutes=cfg.pickup_lead_min)
    taken = set(PickupAppointment.objects.filter(starts_at__gte=now).values_list("starts_at", flat=True))
    zone = timezone.get_current_timezone()
    out = []
    for row in capacity_selectors.operating_days(local.date(), cfg.pickup_horizon_days):
        slots = []
        for minute in domain.slot_starts(row.opens, row.closes, row.breaks, cfg.pickup_slot_min):
            start = datetime.combine(row.day, time(minute // 60, minute % 60), tzinfo=zone)
            if start >= earliest and start not in taken:
                slots.append(start)
        if slots:
            out.append((row.day, slots))
    return out


def _reached_at(order: Order) -> dict[str, datetime]:
    """أول وقت بلغ فيه الطلب كل حالة، من سجل التدقيق."""
    rows = (
        AuditLog.objects.filter(action="orders.transition", target=f"order:{order.pk}")
        .order_by("created_at", "id")
        .values_list("payload", "created_at")
    )
    reached: dict[str, datetime] = {}
    for payload, at in rows:
        reached.setdefault(payload.get("to", ""), at)
    return reached


def _appointment_out(appointment: PickupAppointment | None) -> dict[str, Any] | None:
    if appointment is None:
        return None
    return {
        "starts_at": appointment.starts_at,
        "ends_at": appointment.starts_at + timedelta(minutes=appointment.duration_min),
    }


def tracking_view(order: Order) -> dict[str, Any]:
    """ما يراه حامل الرابط السري: الحالة وخطواتها والبنود والمبلغ والموعد. لا اسم ولا بيان شخصي."""
    reached = _reached_at(order)
    path = domain.steps(
        storefront=order.channel == Order.Channel.STOREFRONT,
        fulfillment=order.fulfillment,
        reviewed=order.status == Status.UNDER_REVIEW or Status.UNDER_REVIEW in reached,
    )
    rows = list(order.items.select_related("template", "material", "design_variant"))
    items = [
        {
            "name": item.template.name,
            "name_en": item.template.name_en,
            "variant_code": item.design_variant.code if item.design_variant else "",
            "material_name": item.material.name,
            "material_name_en": item.material.name_en,
            "quantity": item.quantity,
            "line_total": item.unit_price * item.quantity,
        }
        for item in rows
    ]
    subtotal = sum((item.unit_price * item.quantity for item in rows), Decimal("0"))
    delivery = Delivery.objects.filter(order=order).select_related("zone").first()
    appointment = PickupAppointment.objects.filter(order=order).first()
    return {
        "status": order.status,
        "fulfillment": order.fulfillment,
        "steps": [
            {"status": step, "reached": step == order.status or step in reached, "at": reached.get(step)}
            for step in path
        ],
        "items": items,
        "subtotal": subtotal,
        "delivery_fee": order.delivery_fee,
        "total": subtotal + order.delivery_fee,
        "currency": orders_services.CURRENCY,
        "occasion_date": order.occasion_date,
        "delivery_zone": {"name": delivery.zone.name, "name_en": delivery.zone.name_en} if delivery else None,
        "pickup": _appointment_out(appointment),
        "can_book_pickup": can_book_pickup(order),
        "updated_at": order.updated_at,
    }


def upcoming_pickups(*, now: datetime) -> QuerySet[PickupAppointment]:
    """للطاقم: مواعيد لم تُسلَّم طلباتها، من بداية اليوم (ما فات موعده اليوم يبقى ظاهرًا)."""
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return PickupAppointment.objects.filter(
        starts_at__gte=start, order__status=Status.READY_FOR_PICKUP
    ).select_related("order__customer")


def open_deliveries() -> QuerySet[Delivery]:
    """للطاقم: توصيلات طلبات جاهزة أو في الطريق."""
    return (
        Delivery.objects.filter(order__status__in=(Status.READY, Status.OUT_FOR_DELIVERY))
        .select_related("order__customer", "zone")
        .order_by("order__updated_at")
    )
