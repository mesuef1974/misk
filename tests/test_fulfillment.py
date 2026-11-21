"""التتبّع والاستلام والتوصيل: الرابط السري، مواعيد الاستلام وحجزها، مناطق التوصيل ورسومها."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.models import AuditLog
from apps.fulfillment import domain, selectors, services
from apps.fulfillment.models import Delivery, DeliveryZone, FulfillmentConfig, PickupAppointment
from apps.orders.models import Order
from tests.test_checkout import (  # noqa: F401  (case وpay تجهيزتان)
    NAME,
    _add,
    _checkout,
    _json,
    _notify,
    _paid_cart,
    case,
    pay,
)

Status = Order.Status


@pytest.fixture
def zone(db):
    return DeliveryZone.objects.create(name="الدفنة", name_en="Dafna", fee=Decimal("25.00"))


def _ready_pickup_order(client, pay, case, material) -> Order:  # noqa: F811
    """طلب متجر مدفوع بلغ «جاهز». الحالة تُكتب مباشرة: مسار الإنتاج له اختباراته."""
    payment = _paid_cart(client, case, material)
    assert _notify(client, pay, payment).json()["outcome"] == "confirmed"
    Order.objects.filter(pk=payment.order_id).update(status=Status.READY)
    return Order.objects.get(pk=payment.order_id)


def _slots(client, token):
    res = client.get(f"/api/store/track/{token}/pickup-slots")
    assert res.status_code == 200
    return [slot for day in res.json()["days"] for slot in day["slots"]]


def _book(client, token, starts_at, **extra):
    return _json(client, "post", f"/api/store/track/{token}/pickup", {"starts_at": starts_at, **extra})


# ---------- الحساب الخالص ----------


def test_slots_skip_prayer_breaks_and_stop_at_closing():
    starts = domain.slot_starts(840, 1320, [(905, 930), (1100, 1125)], 30)
    assert starts[:2] == [840, 870]
    assert 900 not in starts  # 15:00–15:30 يمسّ التوقف
    assert 930 in starts  # يبدأ عند نهاية التوقف تمامًا
    assert 1080 not in starts and 1110 not in starts
    assert starts[-1] == 1290
    assert domain.slot_starts(840, 860, [], 30) == []
    assert domain.slot_starts(840, 1320, [], 0) == []


def test_steps_follow_channel_and_fulfillment():
    assert domain.steps(storefront=True, fulfillment="pickup", reviewed=False) == [
        "paid",
        "confirmed",
        "in_production",
        "ready",
        "ready_for_pickup",
        "delivered",
    ]
    delivery = domain.steps(storefront=True, fulfillment="delivery", reviewed=True)
    assert delivery[:2] == ["paid", "under_review"] and "out_for_delivery" in delivery
    assert domain.steps(storefront=False, fulfillment="", reviewed=False) == [
        "confirmed",
        "in_production",
        "ready",
        "delivered",
    ]


# ---------- مناطق التوصيل والدفع ----------


@pytest.mark.django_db
def test_public_zones_list_shows_active_only(client, zone):
    DeliveryZone.objects.create(name="الوكرة", fee=Decimal("40.00"), is_active=False)
    body = client.get("/api/store/delivery-zones").json()
    assert body == [{"id": zone.pk, "name": "الدفنة", "name_en": "Dafna", "fee": "25.00"}]


@pytest.mark.django_db
def test_delivery_checkout_requires_an_active_zone(client, case, material, pay, zone):  # noqa: F811
    assert _add(client, case, material, NAME).status_code == 200
    res = _checkout(client, fulfillment="delivery")
    assert res.status_code == 422
    assert res.json()["fields"]["delivery_zone_id"]["code"] == "required"

    zone.is_active = False
    zone.save()
    res = _checkout(client, fulfillment="delivery", delivery_zone_id=zone.pk)
    assert res.status_code == 422
    assert res.json()["fields"]["delivery_zone_id"]["code"] == "invalid_choice"
    assert Order.objects.get().status == Status.DRAFT and not Delivery.objects.exists()


@pytest.mark.django_db
def test_delivery_fee_enters_the_amount_and_is_frozen_on_the_order(client, case, material, pay, zone):  # noqa: F811
    assert _add(client, case, material, NAME).status_code == 200
    res = _checkout(client, fulfillment="delivery", delivery_zone_id=zone.pk)
    assert res.status_code == 200
    body = res.json()
    assert body["amount"] == "110.00"

    order = Order.objects.get()
    assert order.delivery_fee == Decimal("25.00") and order.delivery.zone == zone
    # تعديل رسم المنطقة لا يغيّر ما فُتح دفعه.
    zone.fee = Decimal("60.00")
    zone.save()
    assert _checkout(client, fulfillment="delivery", delivery_zone_id=zone.pk).json()["amount"] == "110.00"

    track = client.get(f"/api/store/track/{body['tracking_token']}?lang=en").json()
    assert track["delivery_fee"] == "25.00" and track["total"] == "110.00"
    assert track["delivery_zone"] == {"name": "الدفنة", "name_en": "Dafna"}
    assert "out_for_delivery" in [step["status"] for step in track["steps"]]
    assert track["can_book_pickup"] is False


@pytest.mark.django_db
def test_pickup_checkout_ignores_a_zone(client, case, material, pay, zone):  # noqa: F811
    assert _add(client, case, material, NAME).status_code == 200
    res = _checkout(client, delivery_zone_id=zone.pk)
    assert res.status_code == 200 and res.json()["amount"] == "85.00"
    assert Order.objects.get().delivery_fee == 0 and not Delivery.objects.exists()


# ---------- التتبّع ----------


@pytest.mark.django_db
def test_tracking_needs_the_secret_link_and_hides_carts(client, case, material, pay):  # noqa: F811
    assert client.get("/api/store/track/nope").status_code == 404
    assert client.get("/api/store/track/" + "x" * 200).status_code == 404
    assert _add(client, case, material, NAME).status_code == 200
    token = Order.objects.get().tracking_token
    res = client.get(f"/api/store/track/{token}?lang=en")
    assert res.status_code == 404 and res.json()["detail"] == "Order not found"


@pytest.mark.django_db
def test_tracking_shows_progress_without_personal_data(client, case, material, pay):  # noqa: F811
    payment = _paid_cart(client, case, material)
    token = payment.order.tracking_token
    stranger = Client()  # الرابط وحده يكفي: لا جلسة ولا دخول
    body = stranger.get(f"/api/store/track/{token}").json()
    assert body["status"] == "awaiting_payment" and body["status_label"] == "بانتظار الدفع"
    assert not any(step["reached"] for step in body["steps"])

    assert _notify(client, pay, payment).json()["outcome"] == "confirmed"
    res = stranger.get(f"/api/store/track/{token}?lang=en")
    body = res.json()
    assert body["status"] == "confirmed" and body["status_label"] == "Confirmed"
    reached = {step["status"]: step for step in body["steps"]}
    assert reached["paid"]["reached"] and reached["paid"]["at"] and reached["confirmed"]["reached"]
    assert not reached["in_production"]["reached"] and reached["in_production"]["at"] is None
    assert reached["paid"]["label"] == "Paid"
    assert body["items"] == [
        {
            "name": "كفر جلد",
            "name_en": "Leather case",
            "material_name": "جلد نباتي",
            "material_name_en": "",
            "quantity": 1,
            "line_total": "85.00",
        }
    ]
    assert body["total"] == "85.00" and body["currency"] == "QAR" and body["pickup"] is None
    assert "نورة" not in res.content.decode() and "customer" not in res.content.decode()


# ---------- حجز موعد الاستلام ----------


@pytest.mark.django_db
def test_booking_opens_only_when_a_pickup_order_is_ready(client, case, material, pay):  # noqa: F811
    payment = _paid_cart(client, case, material)
    token = payment.order.tracking_token
    assert _notify(client, pay, payment).status_code == 200
    assert client.get(f"/api/store/track/{token}/pickup-slots").status_code == 409
    soon = (timezone.now() + timedelta(days=1)).isoformat()
    res = _book(client, token, soon, lang="en")
    assert res.status_code == 409 and res.json()["code"] == "pickup_not_open"
    assert _book(client, "nope", soon).status_code == 404


@pytest.mark.django_db
def test_booking_a_slot_moves_the_order_and_is_idempotent(client, case, material, pay):  # noqa: F811
    order = _ready_pickup_order(client, pay, case, material)
    token = order.tracking_token
    slots = _slots(client, token)
    assert slots and len(slots) == len(set(slots))
    lead = timezone.now() + timedelta(minutes=selectors.config().pickup_lead_min)
    assert all(datetime.fromisoformat(slot) >= lead - timedelta(minutes=1) for slot in slots)

    res = _book(client, token, slots[5])
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready_for_pickup" and body["can_book_pickup"] is True
    assert datetime.fromisoformat(body["pickup"]["starts_at"]) == datetime.fromisoformat(slots[5])
    ends = datetime.fromisoformat(body["pickup"]["ends_at"])
    assert ends - datetime.fromisoformat(slots[5]) == timedelta(minutes=30)
    assert slots[5] not in _slots(client, token)

    assert _book(client, token, slots[5]).status_code == 200  # إعادة الإرسال
    assert AuditLog.objects.filter(action="fulfillment.pickup_book").count() == 1

    # تغيير الموعد يحرّر الأول.
    assert _book(client, token, slots[6]).status_code == 200
    appointment = PickupAppointment.objects.get()
    assert appointment.starts_at == datetime.fromisoformat(slots[6]) and appointment.duration_min == 30
    assert slots[5] in _slots(client, token)
    audit = AuditLog.objects.filter(action="fulfillment.pickup_book").latest("id")
    assert audit.target == f"order:{order.pk}" and audit.payload["previous"]


@pytest.mark.django_db
def test_a_slot_serves_one_order_and_off_grid_times_are_refused(client, case, material, pay):  # noqa: F811
    first = _ready_pickup_order(client, pay, case, material)
    second = _ready_pickup_order(Client(), pay, case, material)
    slots = _slots(client, first.tracking_token)
    assert _book(client, first.tracking_token, slots[5]).status_code == 200

    res = _book(client, second.tracking_token, slots[5])
    assert res.status_code == 409 and res.json()["code"] == "slot_taken"
    off_grid = (datetime.fromisoformat(slots[6]) + timedelta(minutes=7)).isoformat()
    res = _book(client, second.tracking_token, off_grid)
    assert res.status_code == 422 and res.json()["code"] == "slot_unavailable"
    past = (timezone.now() - timedelta(days=1)).isoformat()
    assert _book(client, second.tracking_token, past).status_code == 422
    second.refresh_from_db()
    assert second.status == Status.READY and PickupAppointment.objects.count() == 1


@pytest.mark.django_db
def test_slot_length_and_horizon_follow_the_config(client, case, material, pay):  # noqa: F811
    order = _ready_pickup_order(client, pay, case, material)
    FulfillmentConfig.objects.create(pk=1, pickup_slot_min=60, pickup_lead_min=0, pickup_horizon_days=2)
    res = client.get(f"/api/store/track/{order.tracking_token}/pickup-slots").json()
    assert res["slot_min"] == 60 and len(res["days"]) <= 2
    today = timezone.localdate()
    assert all(day["day"] <= (today + timedelta(days=1)).isoformat() for day in res["days"])


@pytest.mark.django_db
def test_delivery_orders_cannot_book_pickup(client, case, material, pay, zone):  # noqa: F811
    assert _add(client, case, material, NAME).status_code == 200
    token = _checkout(client, fulfillment="delivery", delivery_zone_id=zone.pk).json()["tracking_token"]
    Order.objects.update(status=Status.READY)
    with pytest.raises(services.FulfillmentError) as exc:
        services.book_pickup(token=token, starts_at=timezone.now() + timedelta(days=1))
    assert exc.value.code == "pickup_not_open"


# ---------- الطاقم ----------


@pytest.mark.django_db
def test_staff_lists_need_a_staff_session(client, case, material, pay, zone, staff_user):  # noqa: F811
    assert client.get("/api/fulfillment/pickups").status_code == 401
    assert client.get("/api/fulfillment/deliveries").status_code == 401

    order = _ready_pickup_order(client, pay, case, material)
    slot = _slots(client, order.tracking_token)[5]
    assert _book(client, order.tracking_token, slot).status_code == 200
    guest = Client()
    assert _add(guest, case, material, NAME).status_code == 200
    assert _checkout(guest, fulfillment="delivery", delivery_zone_id=zone.pk).status_code == 200
    delivery_order = Order.objects.exclude(pk=order.pk).get()
    Order.objects.filter(pk=delivery_order.pk).update(status=Status.OUT_FOR_DELIVERY)

    staff = Client()
    staff.force_login(staff_user)
    pickups = staff.get("/api/fulfillment/pickups").json()
    assert [row["order_id"] for row in pickups] == [order.pk] and pickups[0]["duration_min"] == 30
    deliveries = staff.get("/api/fulfillment/deliveries").json()
    assert deliveries == [
        {
            "order_id": delivery_order.pk,
            "customer_name": "نورة العلي",
            "status": "out_for_delivery",
            "zone": "الدفنة",
            "delivery_fee": "25.00",
        }
    ]
