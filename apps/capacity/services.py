"""كتابة السعة: إعادة بناء ملخص الأيام من الطابور. idempotent: إعادته تعطي الصفوف نفسها."""

from __future__ import annotations

from datetime import date, datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import domain, selectors
from .models import DailyCapacity


@transaction.atomic
def refresh_summary(*, now: datetime | None = None) -> int:
    """يعيد حساب سعة أيام الأفق وحجز الطابور عليها. يعيد ما فاض عن الأفق بالدقائق."""
    now = timezone.localtime(now)
    today = now.date()
    days = selectors.day_capacities(today, selectors.HORIZON_DAYS, now=now)
    loads, overflow = domain.allocate(days, selectors.backlog_minutes())
    DailyCapacity.objects.filter(day__lt=today).delete()
    stamp = timezone.now()
    DailyCapacity.objects.bulk_create(
        [
            DailyCapacity(
                day=load.day,
                capacity_min=load.capacity_min,
                booked_min=load.booked_min,
                created_at=stamp,
                updated_at=stamp,
            )
            for load in loads
        ],
        update_conflicts=True,
        unique_fields=["day"],
        update_fields=["capacity_min", "booked_min", "updated_at"],
    )
    return overflow


def request_refresh() -> None:
    """بعد تثبيت المعاملة: في عامل Celery إن وُجد (`PLANNING_ASYNC`)، وإلا في الطلب نفسه."""
    from . import tasks

    def run() -> None:
        if settings.PLANNING_ASYNC:
            tasks.refresh_capacity.delay()
        else:
            refresh_summary()

    transaction.on_commit(run)


def ensure_summary(today: date) -> None:
    """أول استعمال يبني الملخص في الطلب نفسه؛ ملخص أمس يُجدَّد في الخلفية ويُجاب من القائم."""
    state = selectors.summary_state(today)
    if state == "missing":
        refresh_summary()
    elif state == "stale":
        request_refresh()
