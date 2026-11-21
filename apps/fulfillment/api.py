"""مسارات التتبّع والاستلام والتوصيل.

العامة بلا دخول: الرابط السري في المسار هو التحقق، ولا كوكي جلسة تعتمد عليه الكتابة فلا رمز CSRF.
الأخطاء بصيغة مسارات المتجر (رمز ثابت ورسالة بلغتين). مسارات الطاقم بجلسة مشرف.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema, Status

from apps.catalog import storefront_api as store
from apps.core.auth import staff_auth
from apps.core.throttling import ClientRateThrottle
from apps.orders.models import Order

from . import selectors, services

Lang = store.Lang

track_router = Router(tags=["تتبّع الطلب"], auth=None, throttle=[ClientRateThrottle("store-track", "60/m")])
BOOK_THROTTLE = ClientRateThrottle("store-pickup-book", "10/m")
zones_router = Router(tags=["التوصيل"], auth=None, throttle=[ClientRateThrottle("store-zones", "60/m")])
staff_router = Router(tags=["الاستلام والتوصيل"], auth=staff_auth)

MESSAGES: store.Messages = {
    **store.MESSAGES,
    "order_not_found": ("الطلب غير موجود", "Order not found"),
    "pickup_not_open": (
        "حجز موعد الاستلام يُفتح حين يجهز الطلب",
        "Pickup booking opens once your order is ready",
    ),
    "slot_unavailable": ("هذا الموعد غير متاح؛ اختر موعدًا آخر", "This slot is not available; pick another"),
    "slot_taken": ("سبقك أحد إلى هذا الموعد؛ اختر موعدًا آخر", "This slot was just taken; pick another"),
}
_STATUS = {"order_not_found": 404, "pickup_not_open": 409, "slot_taken": 409}

STATUS_EN = {
    Order.Status.DRAFT: "Draft",
    Order.Status.AWAITING_PAYMENT: "Awaiting payment",
    Order.Status.PAID: "Paid",
    Order.Status.UNDER_REVIEW: "Under review",
    Order.Status.CONFIRMED: "Confirmed",
    Order.Status.IN_PRODUCTION: "In production",
    Order.Status.READY: "Ready",
    Order.Status.OUT_FOR_DELIVERY: "Out for delivery",
    Order.Status.READY_FOR_PICKUP: "Ready for pickup",
    Order.Status.DELIVERED: "Delivered",
    Order.Status.CANCELLED: "Cancelled",
    Order.Status.REFUNDED: "Refunded",
}


def _label(status: str, lang: Lang) -> str:
    return STATUS_EN[Order.Status(status)] if lang == "en" else Order.Status(status).label


class StepOut(Schema):
    status: str
    label: str
    reached: bool
    at: datetime | None


class TrackItemOut(Schema):
    name: str
    name_en: str
    material_name: str
    material_name_en: str
    quantity: int
    line_total: Decimal


class ZoneNameOut(Schema):
    name: str
    name_en: str


class AppointmentOut(Schema):
    starts_at: datetime
    ends_at: datetime


class TrackOut(Schema):
    status: str
    status_label: str
    fulfillment: str
    steps: list[StepOut]
    items: list[TrackItemOut]
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    currency: str
    occasion_date: date | None
    delivery_zone: ZoneNameOut | None
    pickup: AppointmentOut | None
    can_book_pickup: bool
    updated_at: datetime


class SlotDayOut(Schema):
    day: date
    slots: list[datetime]


class SlotsOut(Schema):
    slot_min: int
    days: list[SlotDayOut]


class BookIn(Schema):
    starts_at: datetime
    lang: Lang = "ar"


class ZoneOut(Schema):
    id: int
    name: str
    name_en: str
    fee: Decimal


class StaffPickupOut(Schema):
    order_id: int
    customer_name: str
    starts_at: datetime
    duration_min: int

    @staticmethod
    def resolve_customer_name(obj) -> str:
        return obj.order.customer.name


class StaffDeliveryOut(Schema):
    order_id: int
    customer_name: str
    status: str
    zone: str
    delivery_fee: Decimal

    @staticmethod
    def resolve_customer_name(obj) -> str:
        return obj.order.customer.name

    @staticmethod
    def resolve_status(obj) -> str:
        return obj.order.status

    @staticmethod
    def resolve_zone(obj) -> str:
        return obj.zone.name

    @staticmethod
    def resolve_delivery_fee(obj) -> Decimal:
        return obj.order.delivery_fee


def _error(code: str, lang: Lang):
    return Status(_STATUS.get(code, 422), store.error_body(code, lang, messages=MESSAGES))


def _track_body(order: Order, lang: Lang) -> dict:
    view = selectors.tracking_view(order)
    view["status_label"] = _label(view["status"], lang)
    for step in view["steps"]:
        step["label"] = _label(step["status"], lang)
    return view


_ERRORS = {404: store.ErrorOut, 409: store.ErrorOut, 422: store.ErrorOut}


@track_router.get("/{token}", response={200: TrackOut, 404: store.ErrorOut})
def track(request: HttpRequest, token: str, lang: Lang = "ar"):
    order = selectors.tracked_order(token)
    if order is None:
        return _error("order_not_found", lang)
    return Status(200, _track_body(order, lang))


@track_router.get("/{token}/pickup-slots", response={200: SlotsOut, **_ERRORS})
def pickup_slots(request: HttpRequest, token: str, lang: Lang = "ar"):
    order = selectors.tracked_order(token)
    if order is None:
        return _error("order_not_found", lang)
    if not selectors.can_book_pickup(order):
        return _error("pickup_not_open", lang)
    days = [{"day": day, "slots": slots} for day, slots in selectors.free_slots(now=timezone.now())]
    return Status(200, {"slot_min": selectors.config().pickup_slot_min, "days": days})


@track_router.post("/{token}/pickup", response={200: TrackOut, **_ERRORS}, throttle=BOOK_THROTTLE)
def book_pickup(request: HttpRequest, token: str, payload: BookIn):
    """يحجز الموعد أو يغيّره. عنوان نقطة الاستلام لا يُعاد هنا: يُرسل في إشعار تأكيد الموعد."""
    try:
        appointment = services.book_pickup(token=token, starts_at=payload.starts_at)
    except services.FulfillmentError as exc:
        return _error(exc.code, payload.lang)
    # يُقرأ الطلب من جديد: الحجز نقل حالته في الخدمة.
    return Status(200, _track_body(Order.objects.get(pk=appointment.order_id), payload.lang))


@zones_router.get("", response=list[ZoneOut])
def delivery_zones(request: HttpRequest):
    return selectors.active_zones()


@staff_router.get("/pickups", response=list[StaffPickupOut])
def staff_pickups(request: HttpRequest):
    return selectors.upcoming_pickups(now=timezone.now())


@staff_router.get("/deliveries", response=list[StaffDeliveryOut])
def staff_deliveries(request: HttpRequest):
    return selectors.open_deliveries()
