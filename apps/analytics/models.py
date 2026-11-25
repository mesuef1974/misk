"""عدّادات أحداث المتجر اليومية: مجاميع وحدها. لا صف لكل زائر ولا عنوان ولا جلسة ولا متصفح، فلا بيانات شخصية.
ولقطة مؤشرات خطة النمو الأسبوعية."""

from __future__ import annotations

from django.db import models

from apps.core.models import TimeStampedModel


class StoreEventCount(models.Model):
    class Kind(models.TextChoices):
        VIEW = "view", "عرض صفحة منتج"
        CART_ADD = "cart_add", "إضافة للسلة"
        CHECKOUT_START = "checkout_start", "بدء دفع"

    day = models.DateField("اليوم", db_index=True)
    kind = models.CharField("الحدث", max_length=16, choices=Kind.choices)
    # «design:<slug>» أو «template:<slug>»؛ فارغ لما يخص السلة كلها (بدء الدفع).
    subject = models.CharField("الموضوع", max_length=140, blank=True)
    count = models.PositiveIntegerField("العدد", default=0)

    class Meta:
        verbose_name = "عدّاد حدث"
        verbose_name_plural = "عدّادات أحداث المتجر"
        ordering = ["-day", "kind", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "kind", "subject"], name="analytics_event_day_kind_subject"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day} {self.get_kind_display()} {self.subject}: {self.count}"


class PlanSnapshot(TimeStampedModel):
    """لقطة مؤشرات خطة النمو لأسبوع ينتهي بـ`week_end` (الأحد إلى السبت). صف واحد لكل أسبوع: إعادة الحساب تستبدله."""

    week_end = models.DateField("آخر يوم في الأسبوع", unique=True)
    # `{معرّف المؤشر: قيمة}` بصيغة `automation/plan.py ingest`؛ ما لا بيانات له غائب.
    metrics = models.JSONField("المؤشرات", default=dict)

    class Meta:
        verbose_name = "لقطة مؤشرات"
        verbose_name_plural = "لقطات مؤشرات الخطة"
        ordering = ["-week_end"]

    def __str__(self) -> str:
        return f"{self.week_end}: {len(self.metrics)} مؤشر"
