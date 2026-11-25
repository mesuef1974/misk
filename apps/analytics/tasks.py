"""مهام Celery للقياس. يجدولها beat يوميًّا (`CELERY_BEAT_SCHEDULE`)."""

from __future__ import annotations

from celery import shared_task
from django.db import OperationalError
from django.utils import timezone

from . import selectors, services


@shared_task(
    name="analytics.snapshot_plan_metrics",
    autoretry_for=(OperationalError,),
    max_retries=3,
    default_retry_delay=10,
)
def snapshot_plan_metrics() -> str:
    """يحفظ لقطة مؤشرات آخر أسبوع مكتمل. يومية لا أسبوعية: تشغيلة فائتة (نشر أو توقف عامل) تعوّضها التالية،
    وإعادتها للأسبوع نفسه تستبدل صفّه. نسب الأحداث ثابتة بعد انتهاء الأسبوع؛ C0.k1 يتبع حال المتجر ساعة الحساب."""
    start, end = selectors.last_week(timezone.localdate())
    snapshot = services.save_snapshot(end, selectors.plan_metrics(start, end))
    return snapshot.week_end.isoformat()
