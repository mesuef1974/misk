from django.contrib import admin

from .models import Placement, RunLog, Sheet


class PlacementInline(admin.TabularInline):
    model = Placement
    extra = 0
    can_delete = False
    readonly_fields = ("order_item", "copy_index", "x_mm", "y_mm", "width_mm", "height_mm")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = ("id", "material", "status", "created_at")
    list_filter = ("status", "material")
    readonly_fields = ("status",)
    list_select_related = ("material",)
    inlines = [PlacementInline]


@admin.register(RunLog)
class RunLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "sheet", "outcome", "duration_s", "material_cost")
    list_filter = ("outcome",)
    list_select_related = ("sheet",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
