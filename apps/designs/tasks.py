"""مهام Celery للتصاميم. التحليل idempotent: إعادته تستبدل نتيجته، فإعادة المهمة بعد انقطاع العامل آمنة."""

from __future__ import annotations

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import OperationalError

from . import services
from .models import DesignVariant


@shared_task(
    name="designs.analyze_variant", autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10
)
def analyze_variant_async(variant_id: int, actor_id: int | None = None) -> str:
    variant = DesignVariant.objects.select_related("design__source").filter(pk=variant_id).first()
    if variant is None:
        return "missing"
    actor = get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
    services.analyze_variant(variant, actor=actor)
    return "error" if variant.analysis_error else "ok"


@shared_task(
    name="designs.reprice_all", autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=10
)
def reprice_all_async() -> int:
    """بعد تغيير إعداد التسعير أو أجرة تجميع أو سعر لوح. idempotent: الناتج من المدخلات القائمة وحدها."""
    return services.reprice_all()
