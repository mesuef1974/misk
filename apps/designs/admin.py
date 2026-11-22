from django.contrib import admin, messages
from django.db import transaction

from . import selectors, services, tasks
from .models import (
    Design,
    DesignFile,
    DesignImage,
    DesignPack,
    DesignPricing,
    DesignSource,
    DesignVariant,
    VariantEstimate,
)


@admin.register(DesignSource)
class DesignSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "license_kind"]
    search_fields = ["name"]


@admin.register(DesignPack)
class DesignPackAdmin(admin.ModelAdmin):
    list_display = ["title", "listing_id", "source"]
    list_filter = ["source"]
    search_fields = ["title", "listing_id"]


VARIANT_COLUMNS = (
    "code",
    "sheet_width_mm",
    "sheet_height_mm",
    "analyzed_at",
    "analysis_error",
)


class VariantInline(admin.TabularInline):
    model = DesignVariant
    fields = VARIANT_COLUMNS
    readonly_fields = VARIANT_COLUMNS
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class ImageInline(admin.TabularInline):
    model = DesignImage
    fields = ["file", "alt_ar", "alt_en", "sort"]
    extra = 1


@admin.register(Design)
class DesignAdmin(admin.ModelAdmin):
    list_display = ["name_original", "name_ar", "category", "status", "is_listed", "listing_state", "source"]
    list_filter = ["status", "is_listed", "source", "category"]
    search_fields = ["name_original", "name_ar", "name_en", "tags"]
    readonly_fields = ["status", "product_template", "slug", "is_listed", "listing_state"]
    inlines = [ImageInline, VariantInline]
    actions = ["approve", "list_in_store", "unlist_from_store"]

    @admin.display(description="ينقصه للنشر")
    def listing_state(self, obj):
        return "، ".join(selectors.listing_blockers(obj)) or "—"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "assembly_fee" in form.changed_data:
            for variant in obj.variants.all():
                services.refresh_estimates(variant)

    @admin.action(description="انشر في المتجر")
    def list_in_store(self, request, queryset):
        for design in queryset.select_related("source"):
            try:
                services.list_design(design, actor=request.user)
            except services.DesignError as exc:
                self.message_user(request, f"{design}: {exc}", messages.ERROR)

    @admin.action(description="أخفِ من المتجر")
    def unlist_from_store(self, request, queryset):
        for design in queryset:
            services.unlist_design(design, actor=request.user)

    @admin.action(description="اعتماد التصاميم المحددة")
    def approve(self, request, queryset):
        for design in queryset:
            try:
                services.approve(design, actor=request.user)
            except services.DesignError as exc:
                self.message_user(request, f"{design}: {exc}", messages.ERROR)


FILE_COLUMNS = (
    "role",
    "fmt",
    "name",
    "file",
    "external_path",
    "size_bytes",
)


class FileInline(admin.TabularInline):
    model = DesignFile
    fields = FILE_COLUMNS
    readonly_fields = FILE_COLUMNS
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


ESTIMATE_COLUMNS = (
    "material",
    "seconds",
    "total_seconds",
    "complete",
    "material_cost",
    "price",
)


class EstimateInline(admin.TabularInline):
    model = VariantEstimate
    fields = ESTIMATE_COLUMNS
    readonly_fields = ESTIMATE_COLUMNS
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DesignVariant)
class DesignVariantAdmin(admin.ModelAdmin):
    list_display = ["__str__", "sheet_width_mm", "sheet_height_mm", "sale_scale_percent", "analyzed_at"]
    list_filter = ["design__source"]
    readonly_fields = [
        "design",
        "code",
        "folder_path",
        "svg_sha256",
        "sheet_width_mm",
        "sheet_height_mm",
        "analysis",
        "analysis_error",
        "analyzed_at",
    ]
    inlines = [FileInline, EstimateInline]
    actions = ["analyze", "fit_to_sheet"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "sale_scale_percent" in form.changed_data:
            # المقاس والأطوال وملف القص تتبع النسبة: تحليل كامل في الخلفية، وهو يعيد التقدير.
            tasks.analyze_variant_async.delay(obj.pk, request.user.pk)
        elif "manual_price" in form.changed_data:
            services.refresh_estimates(obj)

    def has_add_permission(self, request):
        return False

    @admin.action(description="صغِّر مقاس البيع ليسعه اللوح")
    def fit_to_sheet(self, request, queryset):
        for variant in queryset:
            before = variant.sale_scale_percent
            try:
                percent = services.fit_to_sheet(variant, actor=request.user)
            except services.DesignError as exc:
                self.message_user(request, f"{variant}: {exc}", messages.ERROR)
                continue
            if percent != before:
                tasks.analyze_variant_async.delay(variant.pk, request.user.pk)
            self.message_user(request, f"{variant}: {'مقاس الملف' if percent is None else f'{percent}٪'}")

    @admin.action(description="إعادة تحليل النسخ المحددة في الخلفية")
    def analyze(self, request, queryset):
        for variant in queryset:
            tasks.analyze_variant_async.delay(variant.pk, request.user.pk)
        self.message_user(request, f"أُرسل {queryset.count()} للتحليل")


@admin.register(DesignPricing)
class DesignPricingAdmin(admin.ModelAdmin):
    """صف واحد. حفظه أو إجراء «أعد حساب الأسعار» يعيد تسعير الفهرس في الخلفية (بعد تغيير سعر لوح مثلًا)."""

    list_display = ["minute_rate", "margin_pct", "round_to", "updated_at"]
    actions = ["reprice"]

    def has_add_permission(self, request):
        return not DesignPricing.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        services.save_pricing(
            minute_rate=obj.minute_rate, margin_pct=obj.margin_pct, round_to=obj.round_to, actor=request.user
        )
        obj.pk = 1
        transaction.on_commit(tasks.reprice_all_async.delay)

    @admin.action(description="أعد حساب الأسعار")
    def reprice(self, request, queryset):
        tasks.reprice_all_async.delay()
        self.message_user(request, "أُرسلت إعادة الحساب إلى الخلفية")
