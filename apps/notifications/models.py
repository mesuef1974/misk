"""صندوق صادر الإشعارات. حقول وقيود فقط؛ الإرسال في services.py.

لا نصّ رسالة ولا عنوان مستلم هنا: النص يُبنى عند الإرسال من الطلب والقالب، ففيه رابط التتبّع السري
وعنوان نقطة الاستلام، وكلاهما لا يُخزَّن. ورقم العميل بيان شخصي (PDPPL) ينتظر قرار التشفير.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import TimeStampedModel
from apps.orders.models import Customer, Order


class Notification(TimeStampedModel):
    class Kind(models.TextChoices):
        ORDER_RECEIVED = "order_received", "استلمنا طلبك ودفعتك"
        PRODUCTION_STARTED = "production_started", "بدأ الحفر"
        READY = "ready", "جاهز"
        OUT_FOR_DELIVERY = "out_for_delivery", "في الطريق"
        PICKUP_CONFIRMED = "pickup_confirmed", "تأكيد موعد الاستلام"

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار الإرسال"
        SENT = "sent", "أُرسل"
        FAILED = "failed", "تعثّر"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField("النوع", max_length=24, choices=Kind.choices)
    lang = models.CharField("اللغة", max_length=2, choices=Customer.Language.choices)
    # مفتاح idempotency: الحدث نفسه لا يُنتج إشعارين ولو أُعيد أو تزامن.
    dedupe_key = models.CharField(max_length=120, unique=True, editable=False)
    # ما يحتاجه القالب مما لا يُقرأ من الطلب (وقت الموعد المؤكَّد). لا بيان شخصي.
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        "الحالة", max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    provider = models.CharField("المزوّد", max_length=16, blank=True)
    reference = models.CharField("مرجع المزوّد", max_length=120, blank=True)
    attempts = models.PositiveSmallIntegerField("المحاولات", default=0)
    error = models.CharField("سبب التعثّر", max_length=64, blank=True)
    sent_at = models.DateTimeField("وقت الإرسال", null=True, blank=True)

    class Meta:
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — طلب {self.order_id}"
