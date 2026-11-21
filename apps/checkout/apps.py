from django.apps import AppConfig


def _refund_on_cancel(sender, order, **kwargs) -> None:
    """طلب متجر أُلغي وله دفعة مقبوضة (رفض في المراجعة مثلًا): تُستردّ بعد تثبيت الإلغاء."""
    from . import services
    from .models import Payment

    if order.channel != order.Channel.STOREFRONT:
        return
    captured = Payment.objects.filter(order=order, status=Payment.Status.CAPTURED)
    for payment_id in captured.values_list("pk", flat=True):
        services.request_refund(payment_id)


class CheckoutConfig(AppConfig):
    name = "apps.checkout"
    verbose_name = "السلة والدفع"

    def ready(self) -> None:
        from apps.orders.signals import order_cancelled

        order_cancelled.connect(_refund_on_cancel, dispatch_uid="checkout.refund_on_cancel")
