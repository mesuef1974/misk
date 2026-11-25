"""السلة والدفع: سلة الضيف، فتح جلسة الدفع، إشعار المزوّد الموقَّع، المهلة، طابور المراجعة والاسترداد."""

import json
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.analytics.models import StoreEventCount
from apps.capacity.models import Closure
from apps.catalog import designer
from apps.catalog import services as catalog_services
from apps.checkout import providers, services
from apps.checkout.models import Payment, WebhookEvent
from apps.core.models import AuditLog
from apps.orders import services as orders_services
from apps.orders.models import Customer, Order

SECRET = "whsec-test-only"  # pragma: allowlist secret
NAME = {"النمط": "اسم", "النص": "نورة"}
CARD = {"الاسم": "نورة", "الخط": "كايرو"}
FORM = {"customer_name": "  نورة   العلي ", "fulfillment": "pickup"}


@pytest.fixture
def case(material, calibration):
    return catalog_services.upsert_template(
        slug="case",
        name="كفر جلد",
        name_en="Leather case",
        generator="case_name",
        width_mm=Decimal("72"),
        height_mm=Decimal("150"),
        base_price=Decimal("85.00"),
        param_schema=[
            {"name": "النمط", "type": "choice", "choices": ["اسم", "حرفان"]},
            {"name": "النص", "type": "text", "max_length": 20},
        ],
        material_kinds=["leather"],
    )


@pytest.fixture
def plaque(material, calibration):
    return catalog_services.upsert_template(
        slug="plaque",
        name="لوحة معلّقة",
        generator="arched_card",
        width_mm=Decimal("90"),
        height_mm=Decimal("130"),
        base_price=Decimal("120.00"),
        param_schema=[
            {"name": "الاسم", "type": "text", "max_length": 30},
            {"name": "العبارة", "type": "text", "max_length": 60, "required": False},
            {"name": "الخط", "type": "choice", "choices": ["كايرو", "المراي"]},
        ],
        allows_religious_text=True,
    )


@pytest.fixture
def pay(settings):
    settings.PAYMENT_PROVIDER = "test"
    settings.PAYMENT_WEBHOOK_SECRET = SECRET
    return providers.TestProvider(SECRET)


def _json(client, method, path, body=None):
    return getattr(client, method)(path, data=json.dumps(body or {}), content_type="application/json")


def _add(client, template, material, params, **extra):
    sha = designer.render(template, material, params).sha256
    body = {
        "template_slug": template.slug,
        "material_id": material.pk,
        "params": params,
        "sha256": sha,
        "acknowledged": True,
        **extra,
    }
    return _json(client, "post", "/api/store/cart/items", body)


def _checkout(client, **extra):
    return _json(client, "post", "/api/store/cart/checkout", {**FORM, **extra})


def _notify(client, provider, payment, kind=providers.CAPTURED, **override):
    body, headers = provider.signed_event(
        kind=kind,
        session_id=payment.session_id,
        amount=override.get("amount", payment.amount),
        currency=override.get("currency", payment.currency),
        now=override.get("now", time.time()),
    )
    return client.post(
        "/api/payments/webhooks/test",
        data=body,
        content_type="application/json",
        HTTP_X_MISK_SIGNATURE=headers[providers.SIGNATURE_HEADER],
    )


def _paid_cart(client, template, material, params=NAME):
    assert _add(client, template, material, params).status_code == 200
    assert _checkout(client).status_code == 200
    return Payment.objects.select_related("order").latest("id")


# ---------- السلة ----------


@pytest.mark.django_db
def test_guest_cart_roundtrip_with_server_side_price(client, case, material):
    assert client.get("/api/store/cart").json()["status"] == "empty"
    res = _add(client, case, material, NAME, quantity=2, unit_price="1.00")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "draft" and body["total"] == "170.00" and body["currency"] == "QAR"
    item = body["items"][0]
    assert item["unit_price"] == "85.00" and item["name_en"] == "Leather case" and not item["needs_review"]
    assert body["ready_on"] is not None

    order = Order.objects.get()
    assert order.channel == "storefront" and order.status == "draft" and order.tracking_token
    assert len(order.items.get().svg_sha256) == 64

    res = _json(client, "patch", f"/api/store/cart/items/{item['id']}", {"quantity": 3})
    assert res.json()["total"] == "255.00"
    assert _json(client, "patch", "/api/store/cart/items/999999", {"quantity": 3}).status_code == 404
    # زائر آخر لا يرى السلة ولا يعدّلها.
    other = Client()
    assert other.get("/api/store/cart").json()["status"] == "empty"
    assert _json(other, "patch", f"/api/store/cart/items/{item['id']}", {"quantity": 9}).status_code == 422
    assert client.delete(f"/api/store/cart/items/{item['id']}").json()["items"] == []
    assert client.delete(f"/api/store/cart/items/{item['id']}").status_code == 200  # idempotent


@pytest.mark.django_db
def test_cart_rejects_unacknowledged_stale_preview_and_bad_text(client, case, material):
    res = _add(client, case, material, NAME, acknowledged=False, lang="en")
    assert res.status_code == 422 and res.json()["code"] == "not_acknowledged"
    assert res.json()["detail"].startswith("Please confirm")
    res = _add(client, case, material, NAME, sha256="0" * 64)
    assert res.status_code == 422 and res.json()["code"] == "preview_mismatch"
    body = {"template_slug": "case", "material_id": material.pk, "sha256": "0" * 64, "acknowledged": True}
    res = _json(client, "post", "/api/store/cart/items", {**body, "params": {**NAME, "النص": "بسم الله"}})
    assert res.status_code == 422 and res.json()["fields"]["النص"]["code"] == "religious_not_allowed"
    res = _json(client, "post", "/api/store/cart/items", {**body, "params": NAME, "template_slug": "none"})
    assert res.status_code == 404
    assert _add(client, case, material, NAME, quantity=51).status_code == 422
    assert not Order.objects.exists()


@pytest.mark.django_db
def test_unpriced_template_is_not_sellable(client, case, material):
    case.base_price = Decimal("0")
    case.save()
    assert _add(client, case, material, NAME).json()["code"] == "not_for_sale"


@pytest.mark.django_db
def test_cart_writes_require_csrf_token(case, material, pay):
    strict = Client(enforce_csrf_checks=True)
    assert _add(strict, case, material, NAME).status_code == 403
    assert _checkout(strict).status_code == 403
    assert strict.delete("/api/store/cart/items/1").status_code == 403
    assert strict.get("/api/store/cart").status_code == 200


@pytest.mark.django_db
def test_cart_line_limit(client, case, material, monkeypatch):
    monkeypatch.setattr("apps.checkout.cart.MAX_LINES", 1)
    assert _add(client, case, material, NAME).status_code == 200
    assert _add(client, case, material, NAME).json()["code"] == "cart_full"


# ---------- فتح جلسة الدفع ----------


@pytest.mark.django_db
def test_checkout_is_unavailable_without_provider_or_secret(client, case, material, settings):
    _add(client, case, material, NAME)
    res = _checkout(client, lang="en")
    assert res.status_code == 503 and res.json()["code"] == "payments_unavailable"
    settings.PAYMENT_PROVIDER = "test"  # بلا سرّ توقيع: يبقى معطَّلًا
    assert _checkout(client).status_code == 503
    assert Order.objects.get().status == "draft"


@pytest.mark.django_db
def test_checkout_opens_one_session_and_locks_cart(client, case, material, pay):
    assert _checkout(client).json()["code"] == "cart_empty"
    _add(client, case, material, NAME, quantity=2)
    res = _checkout(client, occasion_date=str(timezone.localdate() + timedelta(days=60)), source="instagram")
    assert res.status_code == 200
    body = res.json()
    order = Order.objects.select_related("customer").get()
    payment = Payment.objects.get()
    assert body["amount"] == "170.00" and body["payment_url"] == payment.payment_url
    assert body["tracking_token"] == order.tracking_token
    assert order.status == "awaiting_payment" and order.customer.name == "نورة العلي"
    assert order.fulfillment == "pickup" and order.source == "instagram"
    assert payment.status == "pending" and payment.provider == "test"
    assert AuditLog.objects.filter(action="checkout.start", target=f"order:{order.pk}").count() == 1

    # الإعادة تعيد الجلسة نفسها، والسلة مقفلة والدفع مفتوح.
    assert _checkout(client).json()["payment_url"] == body["payment_url"]
    assert Payment.objects.count() == 1
    counts = {(r.kind, r.subject): r.count for r in StoreEventCount.objects.all()}
    assert counts == {("cart_add", f"template:{case.slug}"): 1}
    cart = client.get("/api/store/cart").json()
    assert cart["status"] == "awaiting_payment" and cart["payment_url"] == body["payment_url"]
    assert _add(client, case, material, NAME).status_code == 409
    item_id = cart["items"][0]["id"]
    assert _json(client, "patch", f"/api/store/cart/items/{item_id}", {"quantity": 1}).status_code == 409


@pytest.mark.django_db
def test_checkout_start_is_counted_once_per_payment_session(
    client, case, material, pay, django_capture_on_commit_callbacks
):
    _add(client, case, material, NAME)
    with django_capture_on_commit_callbacks(execute=True):
        assert _checkout(client).status_code == 200
        assert _checkout(client).status_code == 200
    assert StoreEventCount.objects.get(kind="checkout_start").count == 1


@pytest.mark.django_db
def test_checkout_validates_form_fields(client, case, material, pay):
    _add(client, case, material, NAME)
    yesterday = str(timezone.localdate() - timedelta(days=1))
    res = _checkout(client, fulfillment="drone", source="radio", occasion_date=yesterday, lang="en")
    assert res.status_code == 422
    fields = res.json()["fields"]
    assert {k: v["code"] for k, v in fields.items()} == {
        "fulfillment": "invalid_choice",
        "source": "invalid_choice",
        "occasion_date": "date_in_past",
    }
    assert fields["occasion_date"]["message"] == "The date is in the past"
    assert _checkout(client, customer_name="   ").json()["fields"]["customer_name"]["code"] == "required"
    assert Order.objects.get().status == "draft" and not Payment.objects.exists()


@pytest.mark.django_db
def test_occasion_date_is_refused_when_capacity_cannot_make_it(client, case, material, pay):
    today = timezone.localdate()
    Closure.objects.create(start_date=today, end_date=today + timedelta(days=10))
    _add(client, case, material, NAME)
    res = _checkout(client, occasion_date=str(today + timedelta(days=3)))
    assert res.status_code == 422 and res.json()["code"] == "occasion_too_soon"
    assert res.json()["ready_on"] >= str(today + timedelta(days=11))
    assert _checkout(client, occasion_date=res.json()["ready_on"]).status_code == 200


@pytest.mark.django_db
def test_checkout_refuses_design_that_changed_since_added(client, case, material, pay):
    _add(client, case, material, NAME)
    item = Order.objects.get().items.get()
    case.width_mm = Decimal("60")
    case.save()
    res = _checkout(client)
    assert res.status_code == 422 and res.json()["code"] == "design_changed"
    assert list(res.json()["fields"]) == [str(item.pk)]


# ---------- إشعار المزوّد ----------


def test_signature_rejects_tampering_and_replay():
    provider = providers.TestProvider(SECRET)
    now = time.time()
    body, headers = provider.signed_event(
        kind=providers.CAPTURED, session_id="s", amount=Decimal("85.00"), currency="QAR", now=now
    )
    assert provider.parse_event(body=body, headers=headers, now=now).amount == Decimal("85.00")
    with pytest.raises(providers.SignatureError):
        provider.parse_event(body=body.replace(b"85.00", b"1.00"), headers=headers, now=now)
    with pytest.raises(providers.SignatureError):
        provider.parse_event(body=body, headers=headers, now=now + providers.SIGNATURE_TOLERANCE_S + 1)
    with pytest.raises(providers.SignatureError):
        provider.parse_event(body=body, headers={}, now=now)
    with pytest.raises(providers.SignatureError):
        providers.TestProvider("other").parse_event(body=body, headers=headers, now=now)
    bad = b'{"id": "e", "type": "payment.unknown"}'
    signed = {providers.SIGNATURE_HEADER: providers.sign(SECRET, bad, int(now))}
    with pytest.raises(providers.SignatureError):
        provider.parse_event(body=bad, headers=signed, now=now)


@pytest.mark.django_db
def test_webhook_confirms_paid_order_once(client, case, material, pay):
    payment = _paid_cart(client, case, material)
    # عودة المتصفح وحدها لا تدفع: الطلب ينتظر الإشعار.
    assert payment.order.status == "awaiting_payment"
    assert (
        client.post("/api/payments/webhooks/test", data=b"{}", content_type="application/json").status_code
        == 400
    )
    assert (
        client.post("/api/payments/webhooks/other", data=b"{}", content_type="application/json").status_code
        == 404
    )

    body, headers = pay.signed_event(
        kind=providers.CAPTURED, session_id=payment.session_id, amount=payment.amount, currency="QAR",
        now=time.time(),
    )  # fmt: skip
    send = lambda: client.post(  # noqa: E731
        "/api/payments/webhooks/test", data=body, content_type="application/json",
        HTTP_X_MISK_SIGNATURE=headers[providers.SIGNATURE_HEADER],
    )  # fmt: skip
    assert send().json() == {"ok": True, "outcome": "confirmed"}
    assert send().json() == {"ok": True, "outcome": "duplicate"}

    payment.refresh_from_db()
    order = Order.objects.get()
    assert order.status == "confirmed" and payment.status == "captured" and payment.captured_at
    assert payment.provider_ref == f"txn_{payment.session_id}"
    assert WebhookEvent.objects.count() == 1
    audit = AuditLog.objects.get(action="payment.webhook")
    assert audit.target == f"payment:{payment.pk}" and audit.payload["outcome"] == "confirmed"
    transitions = AuditLog.objects.filter(action="orders.transition", target=f"order:{order.pk}")
    assert [row.payload["to"] for row in transitions.order_by("id")] == [
        "awaiting_payment",
        "paid",
        "confirmed",
    ]
    assert client.get("/api/store/cart").json()["status"] == "empty"
    # حدث جديد للدفعة نفسها لا يعيد القبض.
    assert _notify(client, pay, payment).json()["outcome"] == "already_captured"


@pytest.mark.django_db
def test_webhook_with_wrong_amount_does_not_pay(client, case, material, pay):
    payment = _paid_cart(client, case, material)
    assert _notify(client, pay, payment, amount=Decimal("1.00")).json()["outcome"] == "amount_mismatch"
    assert _notify(client, pay, payment, currency="USD").json()["outcome"] == "amount_mismatch"
    payment.refresh_from_db()
    assert payment.status == "pending" and payment.order.status == "awaiting_payment"
    # جلسة لا نعرفها تُسجَّل ولا تغيّر شيئًا.
    payment.session_id = "missing"
    assert _notify(client, pay, payment).json()["outcome"] == "unknown_session"
    assert AuditLog.objects.filter(action="payment.webhook").count() == 3


@pytest.mark.django_db
def test_failed_payment_allows_a_new_session(client, case, material, pay):
    first = _paid_cart(client, case, material)
    assert _notify(client, pay, first, kind=providers.FAILED).json()["outcome"] == "failed"
    res = _checkout(client)
    assert res.status_code == 200 and res.json()["payment_url"] != first.payment_url
    second = Payment.objects.latest("id")
    assert second.amount == first.amount and Order.objects.get().status == "awaiting_payment"
    assert _notify(client, pay, second).json()["outcome"] == "confirmed"


# ---------- المراجعة والاسترداد ----------


@pytest.mark.django_db
def test_religious_text_waits_for_review_and_rejection_refunds(
    client, plaque, material, pay, staff_user, django_capture_on_commit_callbacks
):
    payment = _paid_cart(client, plaque, material, {**CARD, "العبارة": "ما شاء الله"})
    assert client.get("/api/store/cart").json()["needs_review"] is True
    assert _notify(client, pay, payment).json()["outcome"] == "under_review"
    order = Order.objects.get()
    assert order.status == "under_review"

    staff = Client()
    staff.force_login(staff_user)
    queue = staff.get("/api/orders?status=under_review").json()
    assert queue["items"][0]["items"][0]["review_reasons"] == ["religious_text"]
    with django_capture_on_commit_callbacks(execute=True):
        res = _json(staff, "post", f"/api/orders/{order.pk}/transition", {"to_status": "cancelled"})
    assert res.status_code == 200
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "refunded" and payment.refunded_at and order.status == "refunded"
    assert AuditLog.objects.filter(action="payment.refund", target=f"payment:{payment.pk}").count() == 1
    assert services.refund_payment(payment.pk).status == "refunded"  # لا استرداد ثانٍ
    assert AuditLog.objects.filter(action="payment.refund").count() == 1


@pytest.mark.django_db
def test_review_approval_confirms(client, plaque, material, pay, staff_user):
    payment = _paid_cart(client, plaque, material, {**CARD, "الاسم": "عبدالله"})
    _notify(client, pay, payment)
    order = Order.objects.get()
    assert order.status == "under_review" and order.items.get().review_reasons == ["divine_name"]
    client.force_login(staff_user)
    res = _json(client, "post", f"/api/orders/{order.pk}/transition", {"to_status": "confirmed"})
    assert res.status_code == 200 and res.json()["status"] == "confirmed"


@pytest.mark.django_db
def test_paid_order_without_calibration_waits_for_staff(client, case, material, calibration, pay):
    payment = _paid_cart(client, case, material)
    calibration.delete()
    assert _notify(client, pay, payment).json()["outcome"] == "under_review"


@pytest.mark.django_db
def test_failed_refund_is_retried_by_sweep(
    client, case, material, pay, monkeypatch, django_capture_on_commit_callbacks
):
    payment = _paid_cart(client, case, material)
    _notify(client, pay, payment)
    order = Order.objects.get()

    def down(self, **kwargs):
        raise providers.ProviderError("down")

    with monkeypatch.context() as patch:
        patch.setattr(providers.TestProvider, "refund", down)
        with django_capture_on_commit_callbacks(execute=True):
            orders_services.transition(order_id=order.pk, to_status="cancelled")
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "refund_pending" and order.status == "cancelled"
    later = timezone.now() + services.REFUND_RETRY_AFTER + timedelta(seconds=1)
    assert services.sweep(now=later)["refunds_retried"] == 1
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "refunded" and order.status == "refunded"


# ---------- المهلة ----------


@pytest.mark.django_db
def test_unpaid_order_expires_and_late_payment_is_refunded(
    client, case, material, pay, django_capture_on_commit_callbacks
):
    payment = _paid_cart(client, case, material)
    order = payment.order
    assert services.sweep()["expired"] == 0
    later = timezone.now() + services.checkout_ttl() + timedelta(seconds=1)
    assert services.sweep(now=later) == {"expired": 1, "abandoned": 0, "refunds_retried": 0}
    assert services.sweep(now=later)["expired"] == 0  # idempotent
    payment.refresh_from_db()
    order.refresh_from_db()
    assert order.status == "cancelled" and payment.status == "expired"
    assert AuditLog.objects.filter(action="checkout.expire", target=f"order:{order.pk}").count() == 1
    assert client.get("/api/store/cart").json()["status"] == "empty"

    # العميل دفع بعد المهلة: لا يدخل الطابور، ويُستردّ ما دفع.
    with django_capture_on_commit_callbacks(execute=True):
        assert _notify(client, pay, payment).json()["outcome"] == "late_refund"
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == "refunded" and order.status == "refunded"


@pytest.mark.django_db
def test_expired_cart_reports_expiry_then_starts_fresh(client, case, material, pay):
    payment = _paid_cart(client, case, material)
    Payment.objects.filter(pk=payment.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    res = _checkout(client)
    assert res.status_code == 409 and res.json()["code"] == "cart_expired"
    assert _add(client, case, material, NAME).json()["status"] == "draft"
    assert Order.objects.filter(status="draft").count() == 1


@pytest.mark.django_db
def test_awaiting_payment_holds_capacity_until_expiry(client, case, material, pay):
    from apps.capacity import selectors as capacity_selectors

    _paid_cart(client, case, material)
    assert len(capacity_selectors.backlog_minutes()) == 1
    services.sweep(now=timezone.now() + services.checkout_ttl() + timedelta(seconds=1))
    assert capacity_selectors.backlog_minutes() == []


@pytest.mark.django_db
def test_abandoned_cart_is_deleted_with_its_placeholder_customer(client, case, material):
    _add(client, case, material, NAME)
    assert services.sweep()["abandoned"] == 0
    later = timezone.now() + services.ABANDONED_CART + timedelta(minutes=1)
    assert services.sweep(now=later)["abandoned"] == 1
    assert not Order.objects.exists() and not Customer.objects.exists()


# ---------- محاكاة الطاقم ----------


@pytest.mark.django_db
def test_staff_can_simulate_test_payment_only_with_test_provider(
    client, case, material, pay, staff_user, settings
):
    payment = _paid_cart(client, case, material)
    path = f"/api/payments/test/sessions/{payment.session_id}/captured"
    assert _json(client, "post", path).status_code == 401
    staff = Client()
    staff.force_login(staff_user)
    assert _json(staff, "post", "/api/payments/test/sessions/none/captured").status_code == 404
    assert _json(staff, "post", path).json() == {"ok": True, "outcome": "confirmed"}
    audit = AuditLog.objects.get(action="payment.test_simulate")
    assert audit.actor_name == "staff" and audit.target == f"payment:{payment.pk}"
    settings.PAYMENT_PROVIDER = ""
    assert _json(staff, "post", path).status_code == 404


def test_task_names_are_registered():
    from apps.checkout import tasks

    assert tasks.sweep.name == "checkout.sweep" and tasks.refund_payment.name == "checkout.refund"
