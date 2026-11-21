"""السعة: إعدادها، نوافذ التشغيل، الإغلاقات، وملخص كل يوم. حقول وقيود فقط."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel


class CapacityConfig(TimeStampedModel):
    """صف واحد (pk=1). القيم يضبطها المدير من لوحة الإدارة."""

    machine_ratio_pct = models.PositiveSmallIntegerField(
        "نسبة الماكينة من الحضور %", default=50, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    prayer_break_min = models.PositiveSmallIntegerField(
        "توقف الصلاة (دقيقة)", default=25, validators=[MaxValueValidator(120)]
    )
    friday_prayer_break_min = models.PositiveSmallIntegerField(
        "توقف صلاة الجمعة (دقيقة)", default=60, validators=[MaxValueValidator(180)]
    )
    engrave_fill_pct = models.PositiveSmallIntegerField(
        "تغطية الحفر من المساحة الآمنة %",
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    handling_s_per_piece = models.PositiveSmallIntegerField("مناولة القطعة (ثانية)", default=60)
    fallback_piece_min = models.PositiveSmallIntegerField(
        "زمن القطعة بلا معايرة حفر (دقيقة)", default=10, validators=[MinValueValidator(1)]
    )
    latitude = models.DecimalField("خط العرض", max_digits=7, decimal_places=4, default=Decimal("25.2854"))
    longitude = models.DecimalField("خط الطول", max_digits=7, decimal_places=4, default=Decimal("51.5310"))

    class Meta:
        verbose_name = "إعداد السعة"
        verbose_name_plural = "إعداد السعة"

    def __str__(self) -> str:
        return "إعداد السعة"


class OperatingWindow(TimeStampedModel):
    """نافذة الحضور ليوم من الأسبوع. يوم بلا نافذة مغلق."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "الاثنين"
        TUESDAY = 1, "الثلاثاء"
        WEDNESDAY = 2, "الأربعاء"
        THURSDAY = 3, "الخميس"
        FRIDAY = 4, "الجمعة"
        SATURDAY = 5, "السبت"
        SUNDAY = 6, "الأحد"

    weekday = models.PositiveSmallIntegerField("اليوم", choices=Weekday.choices, unique=True)
    opens = models.TimeField("من")
    closes = models.TimeField("إلى")

    class Meta:
        verbose_name = "نافذة تشغيل"
        verbose_name_plural = "نوافذ التشغيل"
        ordering = ["weekday"]
        constraints = [
            models.CheckConstraint(condition=Q(closes__gt=F("opens")), name="window_closes_after_opens"),
        ]

    def __str__(self) -> str:
        return f"{self.get_weekday_display()} {self.opens:%H:%M}–{self.closes:%H:%M}"


class Closure(TimeStampedModel):
    """يوم مغلق أو إغلاق موسمي (الطرفان داخلان)."""

    start_date = models.DateField("من")
    end_date = models.DateField("إلى")
    reason = models.CharField("السبب", max_length=120, blank=True)

    class Meta:
        verbose_name = "إغلاق"
        verbose_name_plural = "الإغلاقات"
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="closure_end_not_before_start"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.start_date} – {self.end_date} {self.reason}".strip()


class DailyCapacity(TimeStampedModel):
    """ملخص يوم: دقائق الماكينة المتاحة وما حجزه الطابور منها. تكتبه `services.refresh_summary` وحدها."""

    day = models.DateField(unique=True)
    capacity_min = models.PositiveIntegerField()
    booked_min = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "سعة يوم"
        verbose_name_plural = "سعة الأيام"
        ordering = ["day"]
        constraints = [
            models.CheckConstraint(
                condition=Q(booked_min__lte=F("capacity_min")), name="booked_within_capacity"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day}: {self.booked_min}/{self.capacity_min}"
