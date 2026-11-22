"""الدفع: فتح الجلسة، معالجة إشعار المزوّد، مهلة غير المدفوع، والاسترداد. كلها idempotent.

- الطلب يصير «مدفوعًا» من إشعار المزوّد الموقَّع وحده، لا من عودة المتصفح.
- نداء المزوّد يجري خارج معاملة قاعدة البيانات: لا قفل صفّ ينتظر شبكة.
- ما دُفع بعد إلغاء طلبه (إشعار متأخر عن المهلة) يُستردّ آليًّا.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.capacity import selectors as capacity_selectors
from apps.capacity import services as capacity_services
from apps.catalog import designer
from apps.catalog import domain as catalog_domain
from apps.core.columns import column_length
from apps.core.services import record_audit
from apps.designs import selectors as design_selectors
from apps.fulfillment import selectors as fulfillment_selectors
from apps.fulfillment import services as fulfillment_services
from apps.fulfillment.models import DeliveryZone
from apps.orders import services as orders_services
from apps.orders.models import Customer, Order

from . import cart, providers
from .models import Payment, WebhookEvent

logger = logging.getLogger(__name__)

Status = Order.Status
CURRENCY = orders_services.CURRENCY
NAME_LENGTH = column_length(Customer, "name")
# سلة لم تُفتح لها جلسة دفع ومضى عليها يوم: جلسة صاحبها انتهت (8 ساعات) فلا يصلها أحد.
ABANDONED_CART = timedelta(hours=24)
REFUND_RETRY_AFTER = timedelta(minutes=5)


class CheckoutError(Exception):
    """رفض لطلب الدفع. `code` رمز ثابت، و`ready_on` أقرب جاهزية حين يكون السبب تاريخ المناسبة."""

    def __init__(self, code: str, *, ready_on: date | None = None, fields: dict[str, str] | None = None):
        super().__init__(code)
        self.code = code
        self.ready_on = ready_on
        self.fields = fields or {}


@dataclass(frozen=True)
class CheckoutForm:
    customer_name: str
    fulfillment: str
    occasion_date: date | None = None
    notes: str = ""
    source: str = ""
    delivery_zone_id: int | None = None
    lang: str = Customer.Language.AR


def checkout_ttl() -> timedelta:
    return timedelta(minutes=settings.CHECKOUT_TTL_MIN)


def items_total(order: Order) -> Decimal:
    return sum((item.unit_price * item.quantity for item in order.items.all()), Decimal("0"))


def order_amount(order: Order) -> Decimal:
    return items_total(order) + order.delivery_fee


def _delivery_zone(form: CheckoutForm) -> DeliveryZone | None:
    """منطقة التوصيل المختارة. الموقوفة أو المجهولة تُرفض؛ الاستلام بلا منطقة."""
    if form.fulfillment != Order.Fulfillment.DELIVERY:
        return None
    zone = fulfillment_selectors.active_zone(form.delivery_zone_id)
    if zone is None:
        raise CheckoutError("invalid", fields={"delivery_zone_id": "invalid_choice"})
    return zone


def _attempt_amount(order: Order, zone: DeliveryZone | None) -> Decimal:
    """مبلغ هذه المحاولة: المسودة برسم منطقتها المختارة الآن، وما فُتح دفعه برسمه المثبَّت."""
    if order.status == Status.DRAFT:
        return items_total(order) + (zone.fee if zone else Decimal("0"))
    return order_amount(order)


def ready_on(order: Order, *, now: datetime) -> date | None:
    """أقرب يوم يجهز فيه الطلب لو دخل الطابور الآن. None: لا يتسع له الأفق."""
    local = timezone.localtime(now)
    capacity_services.ensure_summary(local.date())
    return capacity_selectors.earliest_ready(capacity_selectors.order_minutes(order.pk), now=local)


def _clean_form(form: CheckoutForm, *, today: date) -> CheckoutForm:
    errors: dict[str, str] = {}
    name = " ".join(form.customer_name.split())
    if not name:
        errors["customer_name"] = "required"
    elif len(name) > NAME_LENGTH:
        errors["customer_name"] = "too_long"
    if form.fulfillment not in Order.Fulfillment.values:
        errors["fulfillment"] = "invalid_choice"
    delivery = form.fulfillment == Order.Fulfillment.DELIVERY
    if delivery and form.delivery_zone_id is None:
        errors["delivery_zone_id"] = "required"
    if form.source and form.source not in Order.Source.values:
        errors["source"] = "invalid_choice"
    if len(form.notes) > orders_services.MAX_NOTES_LENGTH:
        errors["notes"] = "too_long"
    if form.occasion_date is not None and form.occasion_date < today:
        errors["occasion_date"] = "date_in_past"
    if errors:
        raise CheckoutError("invalid", fields=errors)
    zone_id = form.delivery_zone_id if delivery else None
    lang = form.lang if form.lang in Customer.Language.values else Customer.Language.AR
    return CheckoutForm(name, form.fulfillment, form.occasion_date, form.notes, form.source, zone_id, lang)


def _recheck_items(order: Order) -> None:
    """القالب أو المعايرة أو قائمة الكلمات قد تتغير والسلة مفتوحة: ما لا يُرسم اليوم كما أُقرّ لا يُباع."""
    changed = []
    for item in order.items.select_related("template", "material"):
        if item.design_variant_id is not None:
            # تصميم جاهز: لا رسم يُعاد. يُباع ما دام منشورًا وسعره على مادته هو ما أُضيف به.
            if design_selectors.current_price(item.design_variant_id, item.material_id) != item.unit_price:
                changed.append(item.pk)
            continue
        try:
            if not item.template.is_active:
                raise designer.DesignUnavailableError("not_found")
            rendered = designer.render(item.template, item.material, item.params)
        except (designer.DesignUnavailableError, designer.DesignRejectedError, catalog_domain.ParamError):
            changed.append(item.pk)
            continue
        if rendered.sha256 != item.svg_sha256:
            changed.append(item.pk)
        elif rendered.review_reasons != item.review_reasons:
            item.review_reasons = rendered.review_reasons
            item.save(update_fields=["review_reasons", "updated_at"])
    if changed:
        raise CheckoutError("design_changed", fields={str(pk): "design_changed" for pk in changed})


def _live_payment(order: Order, now: datetime) -> Payment | None:
    return order.payments.filter(status=Payment.Status.PENDING, expires_at__gt=now).first()


def start_checkout(*, cart_ref: uuid.UUID | None, form: CheckoutForm, now: datetime | None = None) -> Payment:
    """يفتح جلسة دفع للسلة وينقلها إلى «بانتظار الدفع». إعادته والجلسة قائمة تعيد الجلسة نفسها.

    طلب بانتظار الدفع فشلت محاولته يُفتح له جلسة جديدة بالمبلغ نفسه دون تغيير بياناته.
    رسم التوصيل من المنطقة المختارة يدخل المبلغ ويُثبَّت على الطلب عند فتح الدفع.
    """
    provider = providers.active()
    if provider is None:
        raise CheckoutError("payments_unavailable")
    now = now or timezone.now()
    sweep(now=now)
    order = cart.find(cart_ref)
    if order is None:
        raise CheckoutError("cart_empty")
    zone = None
    if order.status == Status.AWAITING_PAYMENT:
        if live := _live_payment(order, now):
            return live
    elif order.status == Status.CANCELLED:
        raise CheckoutError("cart_expired")
    elif order.status != Status.DRAFT:
        raise CheckoutError("cart_empty")
    else:
        form = _clean_form(form, today=timezone.localtime(now).date())
        zone = _delivery_zone(form)
        _recheck_items(order)
        ready = ready_on(order, now=now)
        if ready is None:
            raise CheckoutError("no_capacity")
        if form.occasion_date is not None and ready > form.occasion_date:
            raise CheckoutError("occasion_too_soon", ready_on=ready)
    amount = _attempt_amount(order, zone)
    if items_total(order) <= 0:
        raise CheckoutError("cart_empty")
    key = uuid.uuid4()
    try:
        session = provider.create_session(
            idempotency_key=key, amount=amount, currency=CURRENCY, description=f"طلب مسك {order.pk}"
        )
    except providers.ProviderError as exc:
        raise CheckoutError("provider_unavailable") from exc
    return _open_payment(order.pk, form, amount, key, session, provider.name, now)


@transaction.atomic
def _open_payment(
    order_id: int,
    form: CheckoutForm,
    amount: Decimal,
    key: uuid.UUID,
    session: providers.Session,
    provider_name: str,
    now: datetime,
) -> Payment:
    order = Order.objects.select_for_update().select_related("customer").get(pk=order_id)
    if order.status == Status.AWAITING_PAYMENT:
        if live := _live_payment(order, now):  # طلب متزامن سبق: جلسته هي الجلسة
            return live
    elif order.status != Status.DRAFT:
        raise CheckoutError("cart_empty")
    # المسودة يُعاد قراءة منطقتها والطلب مقفول: منطقة أُوقفت أو تغيّر رسمها بين الحساب والقفل لا تمر.
    zone = _delivery_zone(form) if order.status == Status.DRAFT else None
    if _attempt_amount(order, zone) != amount:  # السلة أو الرسم تغيّرا بين الحساب والقفل
        raise CheckoutError("cart_changed")
    # جلسة انتهت مهلتها ولم تُكنس بعد: تُغلق كي لا تزاحم الجديدة على قيد «جلسة مفتوحة واحدة».
    order.payments.filter(status=Payment.Status.PENDING).update(
        status=Payment.Status.EXPIRED, updated_at=timezone.now()
    )
    if order.status == Status.DRAFT:
        order.customer.name = form.customer_name
        order.customer.language = form.lang
        order.customer.save(update_fields=["name", "language", "updated_at"])
        order.fulfillment = form.fulfillment
        order.occasion_date = form.occasion_date
        order.notes = form.notes
        order.source = form.source
        order.save(update_fields=["fulfillment", "occasion_date", "notes", "source", "updated_at"])
        if zone is not None:
            fulfillment_services.assign_delivery(order=order, zone=zone)
        orders_services.transition(order_id=order.pk, to_status=Status.AWAITING_PAYMENT, system=True)
    payment = Payment.objects.create(
        order=order,
        provider=provider_name,
        session_id=session.session_id,
        idempotency_key=key,
        amount=amount,
        currency=CURRENCY,
        payment_url=session.url,
        expires_at=now + checkout_ttl(),
    )
    record_audit(
        action="checkout.start",
        target=f"order:{order.pk}",
        payload={"payment": payment.pk, "provider": provider_name, "amount": str(amount)},
    )
    _after_commit_sweep(checkout_ttl() + timedelta(seconds=30))
    return payment


# ---------- إشعار المزوّد ----------


def handle_webhook(*, provider_name: str, body: bytes, headers, now: float | None = None) -> str:
    """يتحقق من التوقيع ثم يطبّق الحدث. يعيد نتيجة المعالجة؛ يرمي `LookupError` لمزوّد غير فعّال
    و`providers.SignatureError` لما لا يوثَق به."""
    provider = providers.by_name(provider_name)
    if provider is None:
        raise LookupError(provider_name)
    stamp = timezone.now().timestamp() if now is None else now
    event = provider.parse_event(body=body, headers=headers, now=stamp)
    return apply_event(provider.name, event)


@transaction.atomic
def apply_event(provider_name: str, event: providers.Event) -> str:
    """الحدث المكرَّر (المعرّف نفسه) لا يغيّر شيئًا. المبلغ أو العملة المخالفان لا يُقبض بهما."""
    try:
        with transaction.atomic():
            row = WebhookEvent.objects.create(
                provider=provider_name, event_id=event.event_id, kind=event.kind
            )
    except IntegrityError:
        return "duplicate"
    payment = (
        Payment.objects.select_for_update()
        .filter(provider=provider_name, session_id=event.session_id)
        .first()
    )
    outcome = _apply(payment, event) if payment is not None else "unknown_session"
    row.payment = payment
    row.outcome = outcome
    row.save(update_fields=["payment", "outcome", "updated_at"])
    record_audit(
        action="payment.webhook",
        target=f"payment:{payment.pk}" if payment else f"session:{event.session_id}"[:255],
        payload={
            "provider": provider_name,
            "kind": event.kind,
            "outcome": outcome,
            "amount": str(event.amount),
            "currency": event.currency,
        },
        request_id=event.event_id,
    )
    return outcome


def _apply(payment: Payment, event: providers.Event) -> str:
    if event.kind == providers.FAILED:
        if payment.status != Payment.Status.PENDING:
            return "ignored"
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        return "failed"
    if event.amount != payment.amount or event.currency != payment.currency:
        return "amount_mismatch"
    if payment.status in (
        Payment.Status.CAPTURED,
        Payment.Status.REFUND_PENDING,
        Payment.Status.REFUNDED,
    ):
        return "already_captured"
    payment.status = Payment.Status.CAPTURED
    payment.provider_ref = event.reference[: column_length(Payment, "provider_ref")]
    payment.captured_at = timezone.now()
    payment.save(update_fields=["status", "provider_ref", "captured_at", "updated_at"])

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status != Status.AWAITING_PAYMENT:
        # دُفع بعد المهلة أو لجلسة ثانية لطلب مدفوع: لا يدخل الطابور مرتين، يُستردّ.
        request_refund(payment.pk)
        return "late_refund"
    Payment.objects.filter(order=order, status=Payment.Status.PENDING).update(
        status=Payment.Status.EXPIRED, updated_at=timezone.now()
    )
    orders_services.transition(order_id=order.pk, to_status=Status.PAID, system=True)
    needs_review = any(item.review_reasons for item in order.items.all())
    if not needs_review:
        try:
            with transaction.atomic():
                orders_services.transition(order_id=order.pk, to_status=Status.CONFIRMED, system=True)
            return "confirmed"
        except orders_services.OrderError:
            pass  # خامة فقدت معايرتها بعد الدفع: يقف للطاقم بدل أن يضيع
    orders_services.transition(order_id=order.pk, to_status=Status.UNDER_REVIEW, system=True)
    return "under_review"


# ---------- المهلة والاسترداد ----------


def _after_commit_sweep(delay: timedelta) -> None:
    """مع عامل Celery تُجدول مهمة عند نهاية المهلة؛ بلا عامل يكنس كل طلب دفع ما سبقه."""
    if not settings.PLANNING_ASYNC:
        return
    from . import tasks

    transaction.on_commit(lambda: tasks.sweep.apply_async(countdown=int(delay.total_seconds())))


def sweep(*, now: datetime | None = None) -> dict[str, int]:
    """يلغي ما انتهت مهلة دفعه (فتتحرر سعته)، ويحذف السلال المهجورة، ويعيد استردادًا تعثّر."""
    now = now or timezone.now()
    stale = list(
        Order.objects.filter(channel=Order.Channel.STOREFRONT, status=Status.AWAITING_PAYMENT)
        .exclude(payments__expires_at__gt=now)
        .values_list("pk", flat=True)
    )
    expired = sum(_expire(order_id, now) for order_id in stale)
    abandoned = _drop_abandoned(now)
    stuck = Payment.objects.filter(
        status=Payment.Status.REFUND_PENDING, updated_at__lt=now - REFUND_RETRY_AFTER
    ).values_list("pk", flat=True)
    for payment_id in list(stuck):
        _run_refund(payment_id)
    return {"expired": expired, "abandoned": abandoned, "refunds_retried": len(stuck)}


@transaction.atomic
def _expire(order_id: int, now: datetime) -> int:
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Status.AWAITING_PAYMENT or order.payments.filter(expires_at__gt=now).exists():
        return 0
    order.payments.filter(status=Payment.Status.PENDING).update(
        status=Payment.Status.EXPIRED, updated_at=timezone.now()
    )
    orders_services.transition(order_id=order.pk, to_status=Status.CANCELLED, system=True)
    record_audit(action="checkout.expire", target=f"order:{order.pk}")
    return 1


def _drop_abandoned(now: datetime) -> int:
    """سلة لم تبلغ الدفع ليست طلبًا: تُحذف مع زبونها المؤقت، ولا يبقى لها أثر شخصي."""
    carts = Order.objects.filter(
        channel=Order.Channel.STOREFRONT,
        status=Status.DRAFT,
        created_at__lt=now - ABANDONED_CART,
        payments__isnull=True,
    )
    dropped = 0
    for order in carts.select_related("customer"):
        try:
            with transaction.atomic():
                customer = order.customer
                order.delete()
                customer.delete()
            dropped += 1
        except ProtectedError:
            continue
    return dropped


def request_refund(payment_id: int) -> None:
    """بعد تثبيت المعاملة: في عامل Celery إن وُجد، وإلا في الطلب نفسه. الفشل يُعاد من `sweep`."""

    def run() -> None:
        if settings.PLANNING_ASYNC:
            from . import tasks

            tasks.refund_payment.delay(payment_id)
        else:
            _run_refund(payment_id)

    transaction.on_commit(run)


def _run_refund(payment_id: int) -> None:
    try:
        refund_payment(payment_id)
    except providers.ProviderError:
        logger.warning("تعثّر استرداد الدفعة %s؛ يُعاد لاحقًا", payment_id)


def refund_payment(payment_id: int) -> Payment:
    """استرداد كامل لدفعة مقبوضة. idempotent: مفتاح الدفعة يُرسل للمزوّد، والمُستردّ لا يُستردّ ثانية."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status not in (Payment.Status.CAPTURED, Payment.Status.REFUND_PENDING):
            return payment
        payment.status = Payment.Status.REFUND_PENDING
        payment.save(update_fields=["status", "updated_at"])
    provider = providers.by_name(payment.provider)
    if provider is None:
        raise providers.ProviderError("provider_unavailable")
    reference = provider.refund(
        reference=payment.provider_ref,
        amount=payment.amount,
        currency=payment.currency,
        idempotency_key=payment.idempotency_key,
    )
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status != Payment.Status.REFUND_PENDING:
            return payment
        payment.status = Payment.Status.REFUNDED
        payment.refunded_at = timezone.now()
        payment.save(update_fields=["status", "refunded_at", "updated_at"])
        record_audit(
            action="payment.refund",
            target=f"payment:{payment.pk}",
            payload={"amount": str(payment.amount), "reference": reference},
        )
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if (
            order.status == Status.CANCELLED
            and not order.payments.filter(status__in=(Payment.Status.CAPTURED, Payment.Status.REFUND_PENDING))
            .exclude(pk=payment.pk)
            .exists()
        ):
            orders_services.transition(order_id=order.pk, to_status=Status.REFUNDED, system=True)
    return payment
