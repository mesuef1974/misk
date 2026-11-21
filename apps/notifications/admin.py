from django.contrib import admin

from apps.fulfillment.admin import ReadOnlyAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ("order", "kind", "lang", "status", "provider", "attempts", "error", "sent_at")
    list_filter = ("status", "kind", "lang")
    date_hierarchy = "created_at"
    list_select_related = ("order",)
