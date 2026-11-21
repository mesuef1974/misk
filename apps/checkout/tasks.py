"""مهام Celery للدفع. كلها idempotent، فإعادتها بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task
from django.db import OperationalError

from . import providers, services


@shared_task(name="checkout.sweep", autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10)
def sweep() -> dict[str, int]:
    return services.sweep()


@shared_task(
    name="checkout.refund",
    autoretry_for=(OperationalError, providers.ProviderError),
    max_retries=5,
    retry_backoff=30,
)
def refund_payment(payment_id: int) -> str:
    return services.refund_payment(payment_id).status
