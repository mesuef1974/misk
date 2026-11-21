from django.contrib import admin

from .models import Delivery, DeliveryZone, FulfillmentConfig, PickupAppointment


@admin.register(FulfillmentConfig)
class FulfillmentConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not FulfillmentConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "fee", "is_active", "sort_order")
    list_editable = ("fee", "is_active", "sort_order")
    search_fields = ("name", "name_en")


class ReadOnlyAdmin(admin.ModelAdmin):
    """للاطّلاع فقط: تكتبه الخدمات وحدها (الدفع والحجز)، وتعديله من هنا يتجاوز سجل التدقيق."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PickupAppointment)
class PickupAppointmentAdmin(ReadOnlyAdmin):
    list_display = ("order", "starts_at", "duration_min")
    date_hierarchy = "starts_at"
    list_select_related = ("order",)


@admin.register(Delivery)
class DeliveryAdmin(ReadOnlyAdmin):
    list_display = ("order", "zone", "created_at")
    list_filter = ("zone",)
    list_select_related = ("order", "zone")
