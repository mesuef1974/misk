"""الإشعارات 1–4 وتأكيد موعد الاستلام: القوالب بلغتين، الصندوق الصادر، المزوّدات، وإعادة ما تعثّر."""

import logging
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.core.models import AuditLog
from apps.fulfillment.models import DeliveryZone
from apps.notifications import messages, providers, services, tasks
from apps.notifications.models import Notification
from apps.orders import services as orders_services
from apps.orders.models import Order
from tests.test_checkout import (  # noqa: F401  (case وpay تجهيزتان)
    NAME,
    _add,
    _checkout,
    _notify,
    _paid_cart,
    case,
    pay,
)
from tests.test_fulfillment import _book, _slots

Status = Order.Status
Kind = Notification.Kind
OPERATOR = "operator@example.test"
BASE = "https://misk.example.test"
ADDRESS = "الدوحة، شارع 1، بيت 2"
ARABIC = re.compile(r"[؀-ۿ]")


@pytest.fixture
def notify(settings):
    settings.NOTIFY_PROVIDER = "email"
    settings.NOTIFY_OPERATOR_EMAIL = OPERATOR
    settings.PUBLIC_BASE_URL = BASE + "/"
    settings.PICKUP_ADDRESS_AR = ADDRESS
    settings.PICKUP_ADDRESS_EN = ""


def _confirmed_order(client, pay, case, material, commits, **form) -> Order:  # noqa: F811
    """طلب متجر مدفوع ومؤكَّد، وإشعار الاستلام مرسل."""
    assert _add(client, case, material, NAME).status_code == 200
    token = _checkout(client, **form).json()["tracking_token"]
    order = Order.objects.get(tracking_token=token)
    with commits(execute=True):
        assert _notify(client, pay, order.payments.latest("id")).json()["outcome"] == "confirmed"
    return order


def _reach(order: Order, status: str, commits) -> None:
    """يبلغ الطلب حالة كما تبلّغها الخدمة. «جاهز» يُكتب مباشرة: شرط القصّ له اختباراته في الإنتاج."""
    with commits(execute=True):
        if status == Status.READY:
            Order.objects.filter(pk=order.pk).update(status=status)
            order.refresh_from_db()
            services.on_transition(order)
        else:
            orders_services.transition(order_id=order.pk, to_status=status)


# ---------- القوالب ----------


def test_every_template_renders_in_both_languages():
    fields = {"number": 7, "track_url": "https://x.test/track/t", "when": "2026-12-01 16:30", "address": "A"}
    for template, texts in messages.TEXTS.items():
        assert set(texts) == {"ar", "en"}
        for lang in ("ar", "en"):
            subject, body = messages.render(template, lang, **fields)
            assert "7" in subject and fields["track_url"] in body and "{" not in subject + body
            assert bool(ARABIC.search(body)) is (lang == "ar")
    assert messages.render(messages.READY_PICKUP, "fr", **fields) == messages.render(
        messages.READY_PICKUP, "ar", **fields
    )


# ---------- الإشعارات 1–4 ----------


@pytest.mark.django_db
def test_paid_order_is_notified_once_in_the_checkout_language(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    django_capture_on_commit_callbacks,
):
    order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks, lang="en")
    assert order.customer.language == "en"
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [OPERATOR]  # لا وسيلة اتصال بالعميل بعد
    assert f"#{order.pk}" in sent.subject and not ARABIC.search(sent.body)
    assert f"{BASE}/en/track/{order.tracking_token}" in sent.body

    row = Notification.objects.get()
    assert (row.kind, row.lang, row.status, row.provider, row.attempts) == (
        Kind.ORDER_RECEIVED,
        "en",
        Notification.Status.SENT,
        "email",
        1,
    )
    assert row.sent_at is not None
    audit = AuditLog.objects.get(action="notifications.send")
    assert audit.target == f"order:{order.pk}" and order.tracking_token not in str(audit.payload)

    # الحدث نفسه مرة ثانية، والإرسال مرة ثانية: لا إشعار ثانٍ.
    assert services.on_transition(Order.objects.get(pk=order.pk)) is None  # «مؤكَّد» بلا إشعار
    assert services.enqueue(order=order, kind=row.kind, dedupe_key=row.dedupe_key).pk == row.pk
    assert services.deliver(row.pk).attempts == 1
    assert len(mail.outbox) == 1 and Notification.objects.count() == 1


@pytest.mark.django_db
def test_pickup_order_is_told_when_engraving_starts_and_when_ready(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    django_capture_on_commit_callbacks,
):
    order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    _reach(order, Status.IN_PRODUCTION, django_capture_on_commit_callbacks)
    _reach(order, Status.READY, django_capture_on_commit_callbacks)
    kinds = list(Notification.objects.order_by("id").values_list("kind", flat=True))
    assert kinds == [Kind.ORDER_RECEIVED, Kind.PRODUCTION_STARTED, Kind.READY]
    assert len(mail.outbox) == 3
    assert "بدأنا حفر" in mail.outbox[1].body
    assert "احجز موعد الاستلام" in mail.outbox[2].body
    assert f"{BASE}/track/{order.tracking_token}" in mail.outbox[2].body


@pytest.mark.django_db
def test_delivery_order_is_told_when_ready_and_on_its_way(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    django_capture_on_commit_callbacks,
):
    zone = DeliveryZone.objects.create(name="الدفنة", name_en="Dafna", fee=Decimal("25.00"))
    order = _confirmed_order(
        client,
        pay,
        case,
        material,
        django_capture_on_commit_callbacks,
        fulfillment="delivery",
        delivery_zone_id=zone.pk,
    )
    _reach(order, Status.IN_PRODUCTION, django_capture_on_commit_callbacks)
    _reach(order, Status.READY, django_capture_on_commit_callbacks)
    _reach(order, Status.OUT_FOR_DELIVERY, django_capture_on_commit_callbacks)
    assert "سنبلغك حين يخرج للتوصيل" in mail.outbox[2].body
    assert "في الطريق" in mail.outbox[3].body
    _reach(order, Status.DELIVERED, django_capture_on_commit_callbacks)
    assert len(mail.outbox) == 4  # التسليم بلا إشعار (الإشعار 5 في المرحلة 2)


@pytest.mark.django_db
def test_staff_orders_and_disabled_provider_send_nothing(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    settings,
    notify,
    django_capture_on_commit_callbacks,
):
    payment = _paid_cart(client, case, material)
    order = payment.order
    order.status, order.channel = Status.IN_PRODUCTION, Order.Channel.STAFF
    assert services.on_transition(order) is None

    order.channel = Order.Channel.STOREFRONT
    settings.NOTIFY_PROVIDER = ""
    assert providers.active() is None and services.on_transition(order) is None
    settings.NOTIFY_PROVIDER = "email"
    settings.NOTIFY_OPERATOR_EMAIL = ""  # بلا بريد مشغِّل لا مستلم: معطَّل
    assert providers.active() is None and services.on_transition(order) is None
    assert not Notification.objects.exists() and not mail.outbox


# ---------- تأكيد موعد الاستلام ----------


@pytest.mark.django_db
def test_pickup_confirmation_carries_the_address_and_follows_changes(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    django_capture_on_commit_callbacks,
):
    order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    _reach(order, Status.READY, django_capture_on_commit_callbacks)
    token = order.tracking_token
    slots = _slots(client, token)
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        assert _book(client, token, slots[3]).status_code == 200
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    when = timezone.localtime(timezone.datetime.fromisoformat(slots[3])).strftime("%Y-%m-%d %H:%M")
    assert ADDRESS in body and when in body
    assert ADDRESS not in str(list(Notification.objects.values()))  # العنوان لا يُخزَّن

    with django_capture_on_commit_callbacks(execute=True):
        assert _book(client, token, slots[3]).status_code == 200  # الموعد نفسه: لا إشعار
    assert len(mail.outbox) == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert _book(client, token, slots[6]).status_code == 200
    assert len(mail.outbox) == 2
    assert Notification.objects.filter(kind=Kind.PICKUP_CONFIRMED).count() == 2


@pytest.mark.django_db
def test_missing_address_holds_the_confirmation_until_configured(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    settings,
    notify,
    django_capture_on_commit_callbacks,
):
    settings.PICKUP_ADDRESS_AR = ""
    order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    _reach(order, Status.READY, django_capture_on_commit_callbacks)
    slots = _slots(client, order.tracking_token)
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        assert _book(client, order.tracking_token, slots[2]).status_code == 200  # الحجز لا يتعطّل
    row = Notification.objects.get(kind=Kind.PICKUP_CONFIRMED)
    assert (row.status, row.error) == (Notification.Status.FAILED, "pickup_address_missing")
    assert not mail.outbox

    settings.PICKUP_ADDRESS_AR = ADDRESS
    assert services.flush() == 0  # لم تمضِ المهلة
    assert services.flush(now=timezone.now() + services.RETRY_AFTER + timedelta(seconds=1)) == 1
    assert len(mail.outbox) == 1 and ADDRESS in mail.outbox[0].body


# ---------- التعثّر والإعادة ----------


@pytest.mark.django_db
def test_provider_failure_never_breaks_the_event_and_is_retried(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    def down(self, message):
        raise providers.ProviderError("email_failed")

    with monkeypatch.context() as patch:
        patch.setattr(providers.EmailProvider, "send", down)
        order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
        order.refresh_from_db()
        assert order.status == Status.CONFIRMED  # الدفع ثبت والإشعار تعثّر
        row = Notification.objects.get()
        assert (row.status, row.error, row.attempts) == (Notification.Status.FAILED, "email_failed", 1)
        with pytest.raises(providers.ProviderError):
            services.deliver(row.pk)

    later = timezone.now() + services.RETRY_AFTER + timedelta(seconds=1)
    assert services.flush(now=later) == 1
    row.refresh_from_db()
    assert (row.status, row.error, row.attempts) == (Notification.Status.SENT, "", 3)
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_exhausted_notification_stops_retrying(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    notify,
    django_capture_on_commit_callbacks,
):
    _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    mail.outbox.clear()
    Notification.objects.update(status=Notification.Status.FAILED, attempts=services.MAX_ATTEMPTS)
    row = Notification.objects.get()
    assert services.deliver(row.pk).status == Notification.Status.FAILED
    assert services.flush(now=timezone.now() + timedelta(days=1)) == 0
    assert not mail.outbox


# ---------- المزوّدات والمهام ----------


@pytest.mark.django_db
def test_log_provider_records_the_event_without_its_text(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    settings,
    caplog,
    django_capture_on_commit_callbacks,
):
    settings.NOTIFY_PROVIDER = "log"
    settings.PUBLIC_BASE_URL = BASE
    with caplog.at_level(logging.INFO, logger="apps.notifications.providers"):
        order = _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    assert Notification.objects.get().status == Notification.Status.SENT
    assert f"order={order.pk}" in caplog.text and order.tracking_token not in caplog.text
    assert not mail.outbox


@pytest.mark.django_db
def test_missing_base_url_is_reported_not_sent(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    settings,
    notify,
    django_capture_on_commit_callbacks,
):
    settings.PUBLIC_BASE_URL = ""
    _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    assert Notification.objects.get().error == "public_base_url_missing" and not mail.outbox


@pytest.mark.django_db
def test_worker_path_delivers_through_the_task(
    client,
    case,  # noqa: F811
    material,
    pay,  # noqa: F811
    settings,
    notify,
    django_capture_on_commit_callbacks,
):
    settings.PLANNING_ASYNC = True
    _confirmed_order(client, pay, case, material, django_capture_on_commit_callbacks)
    assert Notification.objects.get().status == Notification.Status.SENT and len(mail.outbox) == 1
    assert tasks.deliver.name == "notifications.deliver" and tasks.flush.name == "notifications.flush"
    assert tasks.flush.apply().get() == 0
