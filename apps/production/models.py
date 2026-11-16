"""الإنتاج: اللوح، ومواضع القطع عليه، وسجل التشغيل. حقول وقيود فقط."""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.catalog.models import Calibration, Material
from apps.core.models import TimeStampedModel
from apps.orders.models import OrderItem


class Sheet(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "مخطَّط"
        DONE = "done", "نُفِّذ"
        SCRAPPED = "scrapped", "تالف"

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="sheets")
    width_mm = models.DecimalField(max_digits=6, decimal_places=1)
    height_mm = models.DecimalField(max_digits=6, decimal_places=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"لوح {self.pk} ({self.material})"


class Placement(TimeStampedModel):
    """قطعة واحدة على اللوح. `copy_index` يميّز نسخ البند الواحد، وبه يصير التخطيط idempotent."""

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="placements")
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="placements")
    copy_index = models.PositiveIntegerField()
    x_mm = models.DecimalField(max_digits=6, decimal_places=1)
    y_mm = models.DecimalField(max_digits=6, decimal_places=1)
    width_mm = models.DecimalField(max_digits=6, decimal_places=1)
    height_mm = models.DecimalField(max_digits=6, decimal_places=1)

    class Meta:
        ordering = ["sheet_id", "y_mm", "x_mm"]
        constraints = [
            models.UniqueConstraint(fields=["order_item", "copy_index"], name="uniq_placement_item_copy"),
        ]

    def __str__(self) -> str:
        return f"{self.order_item} #{self.copy_index} على لوح {self.sheet_id}"


class RunLog(TimeStampedModel):
    """تشغيل واحد للآلة على لوح. الإعدادات والكلفة لقطة وقت التشغيل ولا تتغير بعده."""

    class Outcome(models.TextChoices):
        OK = "ok", "نجح"
        FAILED = "failed", "فشل"

    sheet = models.ForeignKey(Sheet, on_delete=models.PROTECT, related_name="runs")
    calibration = models.ForeignKey(
        Calibration, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    settings_snapshot = models.JSONField(default=dict, blank=True)
    duration_s = models.PositiveIntegerField()
    material_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    notes = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"تشغيل لوح {self.sheet_id}: {self.get_outcome_display()}"
