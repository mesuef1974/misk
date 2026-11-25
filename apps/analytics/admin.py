from django.contrib import admin

from .models import StoreEventCount


@admin.register(StoreEventCount)
class StoreEventCountAdmin(admin.ModelAdmin):
    """للقراءة وحدها: العدّادات يكتبها المتجر، وتعديلها يدويًّا يفسد المؤشرات."""

    list_display = ["day", "kind", "subject", "count"]
    list_filter = ["kind", "day"]
    search_fields = ["subject"]
    date_hierarchy = "day"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
