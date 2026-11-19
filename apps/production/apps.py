from django.apps import AppConfig


def _release_cancelled_order(sender, order, actor=None, **kwargs) -> None:
    from . import services

    services.release_order(order_id=order.pk, actor=actor)


def _require_cut_pieces(sender, order, **kwargs) -> None:
    from apps.orders.services import OrderError

    from . import selectors

    remaining = selectors.uncut_pieces(order.pk)
    if remaining:
        raise OrderError(f"لا «جاهز» قبل قصّ كل قطع الطلب: بقيت {remaining} قطعة لم تُنفَّذ على لوح")


class ProductionConfig(AppConfig):
    name = "apps.production"
    verbose_name = "الإنتاج"

    def ready(self) -> None:
        from apps.orders.signals import order_cancelled, order_ready_requested

        order_cancelled.connect(_release_cancelled_order, dispatch_uid="production.release_cancelled_order")
        order_ready_requested.connect(_require_cut_pieces, dispatch_uid="production.require_cut_pieces")
