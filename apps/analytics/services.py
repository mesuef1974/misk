"""تسجيل أحداث المتجر: زيادة عدّاد اليوم. القياس لا يُفشل طلب العميل أبدًا: الخطأ يُسجَّل ويُبتلع."""

from __future__ import annotations

import logging

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import StoreEventCount

logger = logging.getLogger(__name__)
Kind = StoreEventCount.Kind


def design_subject(slug: str) -> str:
    return f"design:{slug}"


def template_subject(slug: str) -> str:
    return f"template:{slug}"


def _bump(kind: str, subject: str) -> bool:
    rows = StoreEventCount.objects.filter(day=timezone.localdate(), kind=kind, subject=subject)
    return bool(rows.update(count=F("count") + 1))


def record(kind: str, subject: str = "") -> None:
    """يزيد عدّاد اليوم واحدًا، وينشئه عند أول حدث. طلبان متزامنان على عدّاد جديد: الخاسر يعيد الزيادة."""
    try:
        if _bump(kind, subject):
            return
        try:
            with transaction.atomic():
                StoreEventCount.objects.create(day=timezone.localdate(), kind=kind, subject=subject, count=1)
        except IntegrityError:
            _bump(kind, subject)
    except DatabaseError:
        logger.exception("تعذّر تسجيل حدث المتجر %s %s", kind, subject)
