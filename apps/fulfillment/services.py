"""كتابة الاستلام والتوصيل: تثبيت منطقة التوصيل على الطلب، وحجز موعد الاستلام. كلاهما idempotent."""

from __future__ import annotations

from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services import record_audit
from apps.orders import services as orders_services
from apps.orders.models import Order

from . import selectors
from .models import Delivery, DeliveryZone, PickupAppointment

Status = Order.Status


class FulfillmentError(Exception):
    """مخالفة لقاعدة الاستلام أو التوصيل. `code` رمز ثابت تترجمه المسارات."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def assign_delivery(*, order: Order, zone: DeliveryZone) -> Delivery:
    """يثبّت المنطقة ورسمها على الطلب. يُستدعى داخل معاملة فتح الدفع والطلب مقفول.

    الرسم يُنسخ إلى الطلب: ما دُفع لا يتغير بتعديل رسم المنطقة لاحقًا.
    """
    order.delivery_fee = zone.fee
    order.save(update_fields=["delivery_fee", "updated_at"])
    delivery, _ = Delivery.objects.update_or_create(order=order, defaults={"zone": zone})
    return delivery


@transaction.atomic
def book_pickup(*, token: str, starts_at: datetime, now: datetime | None = None) -> PickupAppointment:
    """يحجز موعد الاستلام لحامل رابط التتبّع، أو يغيّره. إعادة الحجز بالموعد نفسه لا تغيّر شيئًا.

    الطلب الجاهز ينتقل بالحجز إلى «جاهز للاستلام». موعدان متزامنان على الخانة نفسها: يفوز الأول
    بقيد التفرّد، والثاني يُرفض بـ `slot_taken`.
    """
    now = now or timezone.now()
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    found = selectors.tracked_order(token)
    if found is None:
        raise FulfillmentError("order_not_found")
    order = Order.objects.select_for_update().get(pk=found.pk)
    if not selectors.can_book_pickup(order):
        raise FulfillmentError("pickup_not_open")
    existing = PickupAppointment.objects.filter(order=order).first()
    if existing is not None and existing.starts_at == starts_at:
        return existing
    free = {slot for _, slots in selectors.free_slots(now=now) for slot in slots}
    if starts_at not in free:
        taken = PickupAppointment.objects.filter(starts_at=starts_at).exists()
        raise FulfillmentError("slot_taken" if taken else "slot_unavailable")
    previous = existing.starts_at if existing else None
    try:
        with transaction.atomic():  # نقطة حفظ: فشل القيد لا يُفسد المعاملة الخارجية
            appointment, _ = PickupAppointment.objects.update_or_create(
                order=order,
                defaults={"starts_at": starts_at, "duration_min": selectors.config().pickup_slot_min},
            )
    except IntegrityError as exc:
        raise FulfillmentError("slot_taken") from exc
    if order.status == Status.READY:
        orders_services.transition(order_id=order.pk, to_status=Status.READY_FOR_PICKUP, system=True)
    record_audit(
        action="fulfillment.pickup_book",
        target=f"order:{order.pk}",
        payload={
            "starts_at": starts_at.isoformat(),
            "previous": previous.isoformat() if previous else None,
        },
    )
    return appointment
