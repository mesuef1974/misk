"""مهام Celery للإشعارات. كلها idempotent، فإعادتها بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task
from django.db import OperationalError

from . import providers, services


@shared_task(
    name="notifications.deliver",
    autoretry_for=(OperationalError, providers.ProviderError),
    max_retries=services.MAX_ATTEMPTS - 1,
    retry_backoff=30,
)
def deliver(notification_id: int) -> str:
    return services.deliver(notification_id).status


@shared_task(
    name="notifications.flush", autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10
)
def flush() -> int:
    return services.flush()
