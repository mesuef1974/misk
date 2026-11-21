from django.contrib import admin

from . import services
from .models import CapacityConfig, Closure, DailyCapacity, OperatingWindow


class _RefreshOnChange(admin.ModelAdmin):
    """أي تعديل هنا يغيّر سعة الأيام: يُعاد بناء الملخص بعد الحفظ أو الحذف."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.request_refresh()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        services.request_refresh()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        services.request_refresh()


@admin.register(CapacityConfig)
class CapacityConfigAdmin(_RefreshOnChange):
    def has_add_permission(self, request):
        return not CapacityConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OperatingWindow)
class OperatingWindowAdmin(_RefreshOnChange):
    list_display = ("weekday", "opens", "closes")


@admin.register(Closure)
class ClosureAdmin(_RefreshOnChange):
    list_display = ("start_date", "end_date", "reason")


@admin.register(DailyCapacity)
class DailyCapacityAdmin(admin.ModelAdmin):
    """للقراءة: يكتبه `refresh_summary` وحده."""

    list_display = ("day", "capacity_min", "booked_min")
    date_hierarchy = "day"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
