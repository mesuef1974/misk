"""كتابة الإشعارات: إدراجها في الصندوق الصادر مع الحدث، ثم إرسالها بعد تثبيته. كلها idempotent.

- الإدراج داخل معاملة الحدث (انتقال الطلب، حجز الموعد): إن أُرجع الحدث لم يبقَ إشعاره.
- الإرسال بعد التثبيت: في عامل Celery إن وُجد، وإلا في الطلب نفسه. فشله لا يُفشل الحدث.
- النص يُبنى عند الإرسال ولا يُخزَّن: فيه رابط التتبّع السري وعنوان نقطة الاستلام.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.services import record_audit
from apps.orders.models import Customer, Order

from . import messages, providers
from .models import Notification

logger = logging.getLogger(__name__)

Kind = Notification.Kind
Status = Order.Status

MAX_ATTEMPTS = 5
RETRY_AFTER = timedelta(minutes=5)
FLUSH_LIMIT = 10

# الإشعارات 1–4 من المواصفات: الحالة التي يبلغها الطلب ← إشعارها.
_KIND_BY_STATUS = {
    Status.PAID: Kind.ORDER_RECEIVED,
    Status.IN_PRODUCTION: Kind.PRODUCTION_STARTED,
    Status.READY: Kind.READY,
    Status.OUT_FOR_DELIVERY: Kind.OUT_FOR_DELIVERY,
}


class MessageError(Exception):
    """الإشعار لا يُبنى بإعداد البيئة الحالي. `code` رمز ثابت يظهر في لوحة الإدارة."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------- الإدراج ----------


def on_transition(order: Order) -> Notification | None:
    """إشعار الحالة التي بلغها طلب المتجر، إن كان لها إشعار. طلبات الطاقم لا إشعار لها."""
    kind = _KIND_BY_STATUS.get(Status(order.status))
    if kind is None or order.channel != Order.Channel.STOREFRONT:
        return None
    return enqueue(order=order, kind=kind, dedupe_key=f"order:{order.pk}:{kind}")


def on_pickup_booked(order: Order, starts_at: datetime) -> Notification | None:
    """تأكيد الموعد بعنوان نقطة الاستلام. كل حجز أو تغيير موعد إشعار، والحجز المعاد لا يبلغ هنا."""
    sent = Notification.objects.filter(order=order, kind=Kind.PICKUP_CONFIRMED).count()
    return enqueue(
        order=order,
        kind=Kind.PICKUP_CONFIRMED,
        dedupe_key=f"order:{order.pk}:{Kind.PICKUP_CONFIRMED}:{sent + 1}",
        context={"starts_at": starts_at.isoformat()},
    )


def enqueue(*, order: Order, kind: str, dedupe_key: str, context: dict | None = None) -> Notification | None:
    """يُستدعى داخل معاملة الحدث. المفتاح المكرَّر يعيد الإشعار الموجود ولا يرسله ثانية."""
    if providers.active() is None:
        return None
    lang = order.customer.language
    row, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "order": order,
            "kind": kind,
            "lang": lang if lang in Customer.Language.values else Customer.Language.AR,
            "context": context or {},
        },
    )
    if created:
        transaction.on_commit(partial(_dispatch, row.pk))
    return row


def _dispatch(notification_id: int) -> None:
    """بعد التثبيت. لا يرمي: الحدث ثبت، وما تعثّر يبقى في الصندوق ويُعاد."""
    try:
        if settings.PLANNING_ASYNC:
            from . import tasks

            tasks.deliver.delay(notification_id)
        else:
            _deliver_quietly(notification_id)
            flush()  # ما حُدِّث للتوّ لم تمضِ مهلته، فلا يُعاد هنا
    except Exception:
        logger.exception("notification dispatch failed id=%s", notification_id)


def _deliver_quietly(notification_id: int) -> None:
    try:
        deliver(notification_id)
    except providers.ProviderError:
        logger.warning("notification delivery failed id=%s", notification_id)


# ---------- الإرسال ----------


def deliver(notification_id: int) -> Notification:
    """يرسل إشعارًا واحدًا. ما أُرسل لا يُرسل ثانية، وما استنفد محاولاته يقف للطاقم.

    الصف مقفول حتى يُجيب المزوّد: محاولتان متزامنتان لا ترسلان مرتين. يرمي `ProviderError` بعد
    حفظ التعثّر، لتعيد المهمة المحاولة.
    """
    failure: providers.ProviderError | None = None
    with transaction.atomic():
        row = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("order__customer")
            .get(pk=notification_id)
        )
        provider = providers.active()
        if row.status == Notification.Status.SENT or row.attempts >= MAX_ATTEMPTS or provider is None:
            return row
        row.attempts += 1
        row.provider = provider.name
        try:
            row.reference = provider.send(build_message(row))[:120]
        except MessageError as exc:
            row.status, row.error = Notification.Status.FAILED, exc.code
        except providers.ProviderError as exc:
            row.status, row.error = Notification.Status.FAILED, str(exc)[:64]
            failure = exc
        else:
            row.status, row.error, row.sent_at = Notification.Status.SENT, "", timezone.now()
            record_audit(
                action="notifications.send",
                target=f"order:{row.order_id}",
                payload={
                    "notification": row.pk,
                    "kind": row.kind,
                    "lang": row.lang,
                    "provider": provider.name,
                },
            )
        row.save(
            update_fields=["status", "error", "attempts", "provider", "reference", "sent_at", "updated_at"]
        )
    if failure is not None:
        raise failure
    return row


def flush(*, now: datetime | None = None) -> int:
    """يعيد ما تعثّر أو بقي بلا إرسال ومضت عليه مهلة، بحدّ في كل نداء. يعيد عدد ما أُرسل."""
    now = now or timezone.now()
    stale = (
        Notification.objects.exclude(status=Notification.Status.SENT)
        .filter(attempts__lt=MAX_ATTEMPTS, updated_at__lt=now - RETRY_AFTER)
        .order_by("created_at")
        .values_list("pk", flat=True)[:FLUSH_LIMIT]
    )
    sent = 0
    for notification_id in list(stale):
        try:
            sent += deliver(notification_id).status == Notification.Status.SENT
        except providers.ProviderError:
            continue
    return sent


# ---------- بناء الرسالة ----------


def recipient(order: Order) -> str:
    """وسيلة الاتصال بالعميل. فارغة اليوم: الهاتف والبريد بيانان شخصيان ينتظران قرار التشفير."""
    return ""


def track_url(token: str, lang: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    if not base:
        raise MessageError("public_base_url_missing")
    prefix = "/en" if lang == Customer.Language.EN else ""
    return f"{base}{prefix}/track/{token}"


def _pickup_fields(row: Notification) -> dict[str, str]:
    address = (
        settings.PICKUP_ADDRESS_EN if row.lang == Customer.Language.EN else ""
    ) or settings.PICKUP_ADDRESS_AR
    if not address:
        raise MessageError("pickup_address_missing")
    starts_at = timezone.localtime(datetime.fromisoformat(row.context["starts_at"]))
    return {"address": address, "when": starts_at.strftime("%Y-%m-%d %H:%M")}


def build_message(row: Notification) -> providers.Message:
    order = row.order
    if not order.tracking_token:
        raise MessageError("tracking_token_missing")
    fields: dict[str, object] = {"number": order.pk, "track_url": track_url(order.tracking_token, row.lang)}
    template: str = row.kind
    if row.kind == Kind.READY:
        delivery = order.fulfillment == Order.Fulfillment.DELIVERY
        template = messages.READY_DELIVERY if delivery else messages.READY_PICKUP
    elif row.kind == Kind.PICKUP_CONFIRMED:
        fields.update(_pickup_fields(row))
    subject, body = messages.render(template, row.lang, **fields)
    return providers.Message(
        order_id=order.pk,
        kind=row.kind,
        lang=row.lang,
        subject=subject,
        body=body,
        idempotency_key=row.dedupe_key,
        to=recipient(order),
    )
