from django.apps import AppConfig


def _on_transition(sender, order, **kwargs) -> None:
    from . import services

    services.on_transition(order)


def _on_pickup_booked(sender, order, appointment, **kwargs) -> None:
    from . import services

    services.on_pickup_booked(order, appointment.starts_at)


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    verbose_name = "الإشعارات"

    def ready(self) -> None:
        from apps.fulfillment.signals import pickup_booked
        from apps.orders.signals import order_transitioned

        order_transitioned.connect(_on_transition, dispatch_uid="notifications.on_transition")
        pickup_booked.connect(_on_pickup_booked, dispatch_uid="notifications.on_pickup_booked")
