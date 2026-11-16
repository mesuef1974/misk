from django.contrib import admin

from .models import Customer, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("svg_sha256",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """الحالة للقراءة فقط هنا: تغييرها يمر من الخدمة حتى تُطبَّق قواعد الانتقال ويُسجَّل التدقيق."""

    list_display = ("id", "customer", "status", "occasion_date", "created_at")
    list_filter = ("status",)
    search_fields = ("customer__name",)
    readonly_fields = ("client_ref", "status")
    list_select_related = ("customer",)
    inlines = [OrderItemInline]
