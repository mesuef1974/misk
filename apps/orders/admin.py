from django.contrib import admin

from .models import Customer, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """البنود تُعدَّل هنا والطلب مسودة فقط. بعد التأكيد تُبنى عليها الألواح والأسعار المتفق عليها،
    فتعديلها من اللوحة يتجاوز الخدمات وسجل التدقيق: تُعرض للقراءة."""

    model = OrderItem
    extra = 0
    readonly_fields = ("svg_sha256",)

    @staticmethod
    def _draft(order: Order | None) -> bool:
        return order is None or order.status == Order.Status.DRAFT

    def has_add_permission(self, request, obj=None):
        return self._draft(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._draft(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._draft(obj) and super().has_delete_permission(request, obj)


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
