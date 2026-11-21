from django.apps import AppConfig


def _refresh_after_transition(sender, order, **kwargs) -> None:
    from . import services

    services.request_refresh()


class CapacityConfigApp(AppConfig):
    name = "apps.capacity"
    verbose_name = "السعة والمواعيد"

    def ready(self) -> None:
        from apps.orders.signals import order_transitioned

        order_transitioned.connect(
            _refresh_after_transition, dispatch_uid="capacity.refresh_after_transition"
        )
