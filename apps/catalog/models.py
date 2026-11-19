"""الكتالوج: المواد، ومعايرتها من قصاصة الاختبار، وقوالب المنتجات. حقول وقيود فقط."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Material(TimeStampedModel):
    class Kind(models.TextChoices):
        LEATHER = "leather", "جلد نباتي الدباغة"
        WOOD = "wood", "خشب"
        ACRYLIC = "acrylic", "أكريليك"
        PAPER = "paper", "ورق مقوّى"
        OTHER = "other", "أخرى"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    thickness_mm = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal("0.1"))]
    )
    sheet_width_mm = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("600"))
    sheet_height_mm = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal("305"))
    sheet_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    supplier = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "مادة"
        verbose_name_plural = "المواد"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "thickness_mm"], name="uniq_material_name_thickness"),
        ]

    def __str__(self) -> str:
        return f"{self.name} {self.thickness_mm} مم"


class Calibration(TimeStampedModel):
    """نتيجة قصاصة اختبار على مادة: الإعدادات التي نجحت وأصغر خط مقروء."""

    class Operation(models.TextChoices):
        ENGRAVE = "engrave", "حفر"
        SCORE = "score", "خط"
        CUT = "cut", "قص"

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="calibrations")
    operation = models.CharField(max_length=8, choices=Operation.choices)
    power_pct = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    speed_mm_s = models.DecimalField(
        max_digits=6, decimal_places=1, validators=[MinValueValidator(Decimal("0.1"))]
    )
    passes = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    lines_per_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    min_line_mm = models.DecimalField(
        max_digits=4, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    measured_on = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "معايرة"
        verbose_name_plural = "المعايرات"
        ordering = ["-measured_on", "-id"]
        indexes = [models.Index(fields=["material", "operation", "measured_on"])]

    def __str__(self) -> str:
        return f"{self.material} / {self.get_operation_display()} / {self.measured_on}"


class ProductTemplate(TimeStampedModel):
    """قالب منتج بمعاملات. `generator` مفتاح مولّد SVG، و`param_schema` وصف حقوله."""

    slug = models.SlugField(max_length=64, unique=True, allow_unicode=True)
    name = models.CharField(max_length=120)
    generator = models.CharField(max_length=64)
    width_mm = models.DecimalField(
        max_digits=6, decimal_places=1, validators=[MinValueValidator(Decimal("1"))]
    )
    height_mm = models.DecimalField(
        max_digits=6, decimal_places=1, validators=[MinValueValidator(Decimal("1"))]
    )
    safe_margin_mm = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("3"))
    param_schema = models.JSONField(default=list, blank=True)
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "قالب منتج"
        verbose_name_plural = "قوالب المنتجات"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
