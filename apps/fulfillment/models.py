"""الاستلام والتوصيل: إعداد المواعيد، مناطق التوصيل ورسومها، وموعد الاستلام المحجوز. حقول وقيود فقط.

لا عنوان توصيل ولا هاتف هنا بعد: كلاهما بيان شخصي (PDPPL) لا يُخزَّن إلا مشفَّرًا،
وحقلاهما يُضافان مع مكتبة التشفير بقرار المالك. عنوان نقطة الاستلام لا يُخزَّن ولا يُعرض على المنصة.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.orders.models import Order


class FulfillmentConfig(TimeStampedModel):
    """صف واحد (pk=1). القيم يضبطها المدير من لوحة الإدارة."""

    pickup_slot_min = models.PositiveSmallIntegerField(
        "مدة موعد الاستلام (دقيقة)", default=30, validators=[MinValueValidator(10), MaxValueValidator(180)]
    )
    pickup_lead_min = models.PositiveSmallIntegerField(
        "أقل مهلة قبل الموعد (دقيقة)", default=60, validators=[MaxValueValidator(1440)]
    )
    pickup_horizon_days = models.PositiveSmallIntegerField(
        "أيام الحجز المعروضة", default=14, validators=[MinValueValidator(1), MaxValueValidator(60)]
    )

    class Meta:
        verbose_name = "إعداد الاستلام"
        verbose_name_plural = "إعداد الاستلام"

    def __str__(self) -> str:
        return "إعداد الاستلام"


class DeliveryZone(TimeStampedModel):
    """منطقة توصيل برسمها. الموقوفة لا تُعرض ولا تُختار، وتبقى لما سبق من طلبات."""

    name = models.CharField("الاسم", max_length=80, unique=True)
    name_en = models.CharField("الاسم بالإنجليزية", max_length=80, blank=True)
    fee = models.DecimalField(
        "الرسم", max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    is_active = models.BooleanField("مفعَّلة", default=True)
    sort_order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        verbose_name = "منطقة توصيل"
        verbose_name_plural = "مناطق التوصيل"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.fee})"


class Delivery(TimeStampedModel):
    """منطقة توصيل الطلب. الرسم المقبوض لقطته في `Order.delivery_fee`، فتعديل رسم المنطقة لا يغيّره."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery")
    zone = models.ForeignKey(DeliveryZone, on_delete=models.PROTECT, related_name="deliveries")

    class Meta:
        verbose_name = "توصيل"
        verbose_name_plural = "التوصيلات"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"توصيل الطلب {self.order_id} إلى {self.zone.name}"


class PickupAppointment(TimeStampedModel):
    """موعد استلام طلب. الموعد الواحد لطلب واحد: قيد التفرّد يحسم الحجز المتزامن."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="pickup_appointment")
    starts_at = models.DateTimeField("يبدأ", unique=True)
    duration_min = models.PositiveSmallIntegerField("المدة (دقيقة)", validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "موعد استلام"
        verbose_name_plural = "مواعيد الاستلام"
        ordering = ["starts_at"]

    def __str__(self) -> str:
        return f"استلام الطلب {self.order_id} في {self.starts_at:%Y-%m-%d %H:%M}"
