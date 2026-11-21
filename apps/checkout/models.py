"""الدفع: محاولة دفع لكل جلسة عند المزوّد، وسجل إشعاراته. حقول وقيود فقط؛ القواعد في services.py.

لا بيانات بطاقات هنا: صفحة الدفع عند المزوّد، وما يُحفظ معرّف الجلسة والمبلغ ومرجع العملية.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.orders.models import Order


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار الدفع"
        CAPTURED = "captured", "مقبوض"
        FAILED = "failed", "فشل"
        EXPIRED = "expired", "انتهت مهلته"
        REFUND_PENDING = "refund_pending", "استرداد جارٍ"
        REFUNDED = "refunded", "مُستردّ"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=32)
    session_id = models.CharField(max_length=128)
    # يُرسل إلى المزوّد عند فتح الجلسة وعند الاسترداد: إعادة النداء لا تفتح جلسة ولا تستردّ مرتين.
    idempotency_key = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    currency = models.CharField(max_length=3, default="QAR")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_url = models.CharField(max_length=500)
    expires_at = models.DateTimeField(db_index=True)
    provider_ref = models.CharField(max_length=128, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "session_id"], name="uniq_payment_provider_session"),
            # جلسة مفتوحة واحدة للطلب: طلبا دفع متزامنان لا يفتحان جلستين.
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status="pending"),
                name="uniq_pending_payment_per_order",
            ),
        ]

    def __str__(self) -> str:
        return f"دفعة {self.pk} ({self.get_status_display()})"


class WebhookEvent(TimeStampedModel):
    """إشعار من المزوّد. قيد التفرّد على (المزوّد، معرّف الحدث) هو مفتاح idempotency: المكرَّر لا يُعالَج."""

    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=128)
    kind = models.CharField(max_length=32)
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    outcome = models.CharField(max_length=32, blank=True)

    class Meta:
        verbose_name = "إشعار دفع"
        verbose_name_plural = "إشعارات الدفع"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_webhook_provider_event"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"
