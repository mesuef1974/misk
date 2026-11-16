"""مهام Celery. كل مهمة idempotent: تُعاد بأمان بعد انقطاع العامل (acks_late)."""

from __future__ import annotations

from celery import shared_task

from . import services


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def audit_async(self, *, action: str, target: str = "", request_id: str = "") -> int:
    row = services.record_audit(action=action, target=target, request_id=request_id)
    return row.pk
