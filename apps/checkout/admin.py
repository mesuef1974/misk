from django.contrib import admin

from .models import Payment, WebhookEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    """للاطّلاع فقط: الدفعات وإشعاراتها تكتبها الخدمات وحدها، وتعديلها من هنا يتجاوز سجل التدقيق."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("id", "order", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("session_id", "provider_ref")
    list_select_related = ("order",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(ReadOnlyAdmin):
    list_display = ("id", "provider", "event_id", "kind", "outcome", "created_at")
    list_filter = ("outcome", "kind")
    search_fields = ("event_id",)
