"""الطلبات. حقول وقيود فقط؛ الانتقالات والقواعد في services.py.

لا هاتف للزبون هنا بعد: رقم الهاتف بيان شخصي (PDPPL) ولا يُخزَّن إلا مشفَّرًا،
وحقله يُضاف مع مكتبة التشفير بقرار المالك.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import Material, ProductTemplate
from apps.core.models import TimeStampedModel


class Customer(TimeStampedModel):
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        AWAITING_PAYMENT = "awaiting_payment", "بانتظار الدفع"
        PAID = "paid", "مدفوع"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        CONFIRMED = "confirmed", "مؤكَّد"
        IN_PRODUCTION = "in_production", "قيد التنفيذ"
        READY = "ready", "جاهز"
        OUT_FOR_DELIVERY = "out_for_delivery", "في الطريق"
        READY_FOR_PICKUP = "ready_for_pickup", "جاهز للاستلام"
        DELIVERED = "delivered", "مُسلَّم"
        CANCELLED = "cancelled", "ملغى"
        REFUNDED = "refunded", "مُستردّ"

    class Channel(models.TextChoices):
        STAFF = "staff", "الطاقم"
        STOREFRONT = "storefront", "المتجر"

    class Fulfillment(models.TextChoices):
        PICKUP = "pickup", "استلام بموعد"
        DELIVERY = "delivery", "توصيل"

    class Source(models.TextChoices):
        INSTAGRAM = "instagram", "إنستغرام"
        TIKTOK = "tiktok", "تيك توك"
        SNAPCHAT = "snapchat", "سناب"
        REFERRAL = "referral", "إحالة"
        BAZAAR = "bazaar", "بازار"
        SEARCH = "search", "بحث"
        OTHER = "other", "أخرى"

    client_ref = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    occasion_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.STAFF, db_index=True)
    fulfillment = models.CharField(max_length=16, choices=Fulfillment.choices, blank=True)
    delivery_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))]
    )
    source = models.CharField(max_length=16, choices=Source.choices, blank=True)
    # رابط التتبّع السري. null للطلبات السابقة (expand)؛ الخدمة تولّده لكل طلب جديد.
    tracking_token = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)

    class Meta:
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"طلب {self.pk} ({self.get_status_display()})"


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    template = models.ForeignKey(ProductTemplate, on_delete=models.PROTECT, related_name="+")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="+")
    params = models.JSONField(default=dict, blank=True)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    svg_sha256 = models.CharField(max_length=64, blank=True)
    # أسباب المراجعة اليدوية من المصمِّم (نص ديني، لفظ الجلالة في اسم). غير فارغ = الطلب يمر بطابور المراجعة.
    review_reasons = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "بند طلب"
        verbose_name_plural = "بنود الطلبات"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.template} × {self.quantity}"
