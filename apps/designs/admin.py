from django.contrib import admin, messages

from . import services, tasks
from .models import Design, DesignFile, DesignPack, DesignSource, DesignVariant, VariantEstimate


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


@admin.register(Design)
class DesignAdmin(admin.ModelAdmin):
    list_display = ["name_original", "name_ar", "category", "status", "source"]
    list_filter = ["status", "source", "category"]
    search_fields = ["name_original", "name_ar", "tags"]
    readonly_fields = ["status", "product_template"]
    inlines = [VariantInline]
    actions = ["approve"]

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
    list_display = ["__str__", "sheet_width_mm", "sheet_height_mm", "analyzed_at"]
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
    actions = ["analyze"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="إعادة تحليل النسخ المحددة في الخلفية")
    def analyze(self, request, queryset):
        for variant in queryset:
            tasks.analyze_variant_async.delay(variant.pk, request.user.pk)
        self.message_user(request, f"أُرسل {queryset.count()} للتحليل")
