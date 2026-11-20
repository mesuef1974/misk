"""مهام Celery للإنتاج. التخطيط idempotent، فإعادة المهمة بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import OperationalError

from . import selectors, services


@shared_task(bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10)
def plan_sheets_async(self, *, material_id: int, actor_id: int | None = None) -> dict:
    """يعيد `{"sheets": [...], "waiting": n}` أو `{"error": ...}`: مخالفة قاعدة العمل نتيجةٌ يعرضها المستخدم لا فشلٌ يُعاد.

    انقطاع قاعدة البيانات وحده يُعاد (`autoretry_for`)؛ التخطيط في معاملة واحدة فلا يبقى منه نصف.
    """
    actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
    try:
        # معرّف المهمة ثابت عبر إعادة التسليم، فإعادتها بعد التثبيت تجد ألواحها.
        sheets = services.plan_sheets(material_id=material_id, actor=actor, request_id=self.request.id or "")
    except services.ProductionError as exc:
        return {"error": str(exc)}
    return {"sheets": [sheet.pk for sheet in sheets], "waiting": selectors.waiting_sheets(material_id)}
