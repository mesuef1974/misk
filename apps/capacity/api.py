"""مسارات السعة للطاقم. المسار العام لصفحة المنتج يأتي مع الكتالوج العام."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from django.utils import timezone
from ninja import Query, Router, Schema
from ninja.errors import HttpError

from apps.core.auth import staff_auth
from apps.orders.models import Order

from . import selectors, services

router = Router(tags=["السعة"], auth=staff_auth)

MAX_DAYS = selectors.HORIZON_DAYS
MAX_MINUTES = 100_000


class DayOut(Schema):
    day: date
    capacity_min: int
    booked_min: int


class EarliestOut(Schema):
    minutes: int
    ready_on: date | None  # null: لا يتسع الأفق


def _earliest(minutes: int) -> dict:
    now = timezone.localtime()
    services.ensure_summary(now.date())
    return {"minutes": minutes, "ready_on": selectors.earliest_ready(minutes, now=now)}


@router.get("/days", response=list[DayOut])
def list_days(request: HttpRequest, days: int = Query(30, ge=1, le=MAX_DAYS)):
    today = timezone.localdate()
    services.ensure_summary(today)
    return selectors.summary(today, days)


@router.get("/earliest", response=EarliestOut)
def earliest(request: HttpRequest, minutes: int = Query(..., ge=1, le=MAX_MINUTES)):
    return _earliest(minutes)


@router.get("/orders/{order_id}/earliest", response=EarliestOut)
def order_earliest(request: HttpRequest, order_id: int):
    """متى يجهز هذا الطلب لو دخل الطابور الآن."""
    if not Order.objects.filter(pk=order_id).exists():
        raise HttpError(404, "الطلب غير موجود")
    return _earliest(selectors.order_minutes(order_id))
