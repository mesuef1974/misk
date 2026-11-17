from django.conf import settings
from django.contrib import admin

from .models import AuditLog

# اللوحة تحمل اسم المنصة لا اسم Django؛ ألوانها في templates/admin/base_site.html.
admin.site.site_header = settings.SITE_TITLE
admin.site.site_title = settings.SITE_TITLE
admin.site.index_title = "لوحة الإدارة"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target", "actor")
    list_filter = ("action",)
    search_fields = ("target", "request_id")
    readonly_fields = ("created_at", "updated_at", "action", "target", "actor", "payload", "request_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
