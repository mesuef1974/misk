"""فهرس التصاميم الجاهزة (docs/designs-catalog.md). حقول وقيود فقط؛ المنطق في services.py."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.catalog.models import Material, ProductTemplate
from apps.core.models import TimeStampedModel

from .validators import validate_showcase_image


class DesignSource(TimeStampedModel):
    """البائع. مفتاح ألوانه يحوّل لون الخط إلى عملية ومادة: {"#e30613": {"operation": "cut", "material": "wood"}}."""

    class License(models.TextChoices):
        UNKNOWN = "unknown", "غير محدد"
        PERSONAL = "personal", "استخدام شخصي"
        COMMERCIAL = "commercial", "استخدام تجاري"

    name = models.CharField(max_length=120, unique=True)
    website = models.URLField(blank=True)
    color_key = models.JSONField(default=dict, blank=True)
    license_kind = models.CharField(max_length=12, choices=License.choices, default=License.UNKNOWN)
    license_note = models.TextField(blank=True)
    instructions = models.FileField(upload_to="designs/sources/", blank=True)

    class Meta:
        verbose_name = "مصدر تصاميم"
        verbose_name_plural = "مصادر التصاميم"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DesignPack(TimeStampedModel):
    source = models.ForeignKey(DesignSource, on_delete=models.PROTECT, related_name="packs")
    listing_id = models.CharField(max_length=64)
    title = models.CharField(max_length=200)

    class Meta:
        verbose_name = "حزمة تصاميم"
        verbose_name_plural = "حزم التصاميم"
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(fields=["source", "listing_id"], name="uniq_pack_source_listing")
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.listing_id})"


class Design(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        APPROVED = "approved", "معتمد"

    source = models.ForeignKey(DesignSource, on_delete=models.PROTECT, related_name="designs")
    pack = models.ForeignKey(
        DesignPack, on_delete=models.PROTECT, null=True, blank=True, related_name="designs"
    )
    name_original = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    # ما يراه العميل في المتجر. `slug` يولَّد عند النشر من الاسم الإنجليزي؛ null قبله.
    name_en = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=80, null=True, blank=True, unique=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    occasion = models.CharField(max_length=80, blank=True)
    tags = models.JSONField(default=list, blank=True)
    assembled_width_mm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    assembled_height_mm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    assembled_depth_mm = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    # بصيغة catalog.ProductTemplate.param_schema نفسها، فتنتقل إلى القالب عند البيع بلا تحويل.
    personalization = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    product_template = models.ForeignKey(
        ProductTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="designs"
    )
    notes = models.TextField(blank=True)
    # أجرة تجميع القطعة بعد القص، تدخل سعر كل نسخة (docs/ready-designs-plan.md).
    assembly_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))]
    )
    # النشر في المتجر غير الاعتماد: المعتمد لا يظهر حتى يُنشر (`services.list_design`).
    is_listed = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "تصميم"
        verbose_name_plural = "التصاميم"
        ordering = ["name_original"]
        constraints = [
            models.UniqueConstraint(fields=["source", "name_original"], name="uniq_design_source_name"),
        ]

    def __str__(self) -> str:
        return self.name_ar or self.name_original


class DesignVariant(TimeStampedModel):
    design = models.ForeignKey(Design, on_delete=models.CASCADE, related_name="variants")
    code = models.CharField(max_length=16, blank=True)
    folder_path = models.CharField(max_length=500)
    svg_sha256 = models.CharField(max_length=64, unique=True)
    sheet_width_mm = models.DecimalField(max_digits=7, decimal_places=1, null=True, blank=True)
    sheet_height_mm = models.DecimalField(max_digits=7, decimal_places=1, null=True, blank=True)
    # مقاس البيع نسبةً من مقاس الملف؛ الفارغ = مقاس الملف. يُطبَّق عند التحليل على المقاس والأطوال وملف القص.
    sale_scale_percent = models.DecimalField(
        "نسبة مقاس البيع ٪",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("10")), MaxValueValidator(Decimal("100"))],
        help_text="للتصميم الأكبر من اللوح. لا تصلح لما يتعاشق بسماكة المادة (صناديق وأرفف): فتحاته تصغر معه.",
    )
    analysis = models.JSONField(default=dict, blank=True)
    analysis_error = models.TextField(blank=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)
    # سعر يدوي يغلب المعادلة على كل مادة.
    manual_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        verbose_name = "نسخة تصميم"
        verbose_name_plural = "نسخ التصاميم"
        ordering = ["design", "code"]
        constraints = [models.UniqueConstraint(fields=["design", "code"], name="uniq_variant_design_code")]

    def __str__(self) -> str:
        return f"{self.design} ({self.code})" if self.code else str(self.design)


class DesignFile(TimeStampedModel):
    class Role(models.TextChoices):
        ORIGINAL = "original", "أصل"
        READY_CUT = "ready_cut", "جاهز للقص"
        ALTERNATE = "alternate", "صيغة بديلة"
        CUT_LAYOUT = "cut_layout", "معاينة القص"
        SIZE_REFERENCE = "size_ref", "مرجع المقاس"
        COVER = "cover", "غلاف"

    variant = models.ForeignKey(DesignVariant, on_delete=models.CASCADE, related_name="files")
    role = models.CharField(max_length=12, choices=Role.choices)
    fmt = models.CharField(max_length=8)
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="designs/files/", blank=True)
    external_path = models.CharField(max_length=500, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)

    class Meta:
        verbose_name = "ملف تصميم"
        verbose_name_plural = "ملفات التصاميم"
        ordering = ["variant", "role", "name"]
        constraints = [
            models.UniqueConstraint(fields=["variant", "role", "sha256"], name="uniq_file_variant_role_sha"),
            models.CheckConstraint(
                condition=~models.Q(file="") | ~models.Q(external_path=""), name="file_stored_or_external"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_role_display()}: {self.name}"


class VariantEstimate(TimeStampedModel):
    """تقدير زمن الماكينة وتكلفة المادة لنسخة على مادة. `seconds` لكل عملية، والفارغة بلا معايرة."""

    variant = models.ForeignKey(DesignVariant, on_delete=models.CASCADE, related_name="estimates")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="design_estimates")
    seconds = models.JSONField(default=dict)
    total_seconds = models.DecimalField(
        max_digits=9, decimal_places=1, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))]
    )
    complete = models.BooleanField(default=False)
    material_area_mm2 = models.DecimalField(max_digits=12, decimal_places=1, default=Decimal("0"))
    material_cost = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0"))
    calibration_ids = models.JSONField(default=list)
    # سعر البيع من `pricing.price`. فارغ: التقدير ناقص أو لا إعداد تسعير، فلا تُعرض النسخة على هذه المادة.
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "تقدير نسخة"
        verbose_name_plural = "تقديرات النسخ"
        ordering = ["variant", "material"]
        constraints = [
            models.UniqueConstraint(fields=["variant", "material"], name="uniq_estimate_variant_material"),
        ]

    def __str__(self) -> str:
        return f"{self.variant} / {self.material}"


class DesignImage(TimeStampedModel):
    """صورة عرض يرفعها المالك للمنتج بعد قصّه. وحدها تُخدَم للزائر؛ ملفات التصميم لا تخرج من الإدارة."""

    design = models.ForeignKey(Design, on_delete=models.CASCADE, related_name="images")
    file = models.FileField(upload_to="designs/showcase/", validators=[validate_showcase_image])
    alt_ar = models.CharField(max_length=200, blank=True)
    alt_en = models.CharField(max_length=200, blank=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "صورة عرض"
        verbose_name_plural = "صور العرض"
        ordering = ["sort", "id"]

    def __str__(self) -> str:
        return f"صورة {self.design}"


class DesignPricing(TimeStampedModel):
    """إعداد التسعير، صف واحد (المفتاح 1). بلاه لا يُحسب سعر ولا يُنشر تصميم."""

    minute_rate = models.DecimalField(
        "أجرة دقيقة الماكينة", max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    margin_pct = models.DecimalField(
        "الهامش ٪", max_digits=5, decimal_places=1, validators=[MinValueValidator(Decimal("0"))]
    )
    round_to = models.DecimalField(
        "التقريب إلى أعلى لأقرب",
        max_digits=5,
        decimal_places=2,
        default=Decimal("5"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        verbose_name = "إعداد تسعير التصاميم"
        verbose_name_plural = "إعداد تسعير التصاميم"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="design_pricing_single_row")]

    def __str__(self) -> str:
        return f"{self.minute_rate} ر.ق/د، هامش {self.margin_pct}٪"
