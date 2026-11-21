"""مهام Celery للسعة. إعادة البناء idempotent، فإعادة المهمة بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task
from django.db import OperationalError

from . import services


@shared_task(
    name="capacity.refresh", autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10
)
def refresh_capacity() -> int:
    return services.refresh_summary()
