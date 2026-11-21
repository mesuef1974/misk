from django.contrib import admin

from .models import Calibration, Material, ProductTemplate


class CalibrationInline(admin.TabularInline):
    model = Calibration
    extra = 0


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "thickness_mm", "sheet_cost", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "name_en", "supplier")
    inlines = [CalibrationInline]


@admin.register(ProductTemplate)
class ProductTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "generator", "width_mm", "height_mm", "base_price", "is_active")
    list_filter = ("is_active", "allows_religious_text")
    search_fields = ("name", "name_en", "slug")
