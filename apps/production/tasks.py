"""مهام Celery للإنتاج. التخطيط idempotent، فإعادة المهمة بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task

from . import services


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def plan_sheets_async(self, *, material_id: int) -> list[int]:
    return [sheet.pk for sheet in services.plan_sheets(material_id=material_id)]
