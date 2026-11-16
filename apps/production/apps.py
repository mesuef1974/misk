from django.apps import AppConfig


def _release_cancelled_order(sender, order, actor=None, **kwargs) -> None:
    from . import services

    services.release_order(order_id=order.pk, actor=actor)


class ProductionConfig(AppConfig):
    name = "apps.production"
    verbose_name = "الإنتاج"

    def ready(self) -> None:
        from apps.orders.signals import order_cancelled

        order_cancelled.connect(_release_cancelled_order, dispatch_uid="production.release_cancelled_order")
