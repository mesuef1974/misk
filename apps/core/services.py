"""طبقة الخدمات: كل عملية كتابة تمرّ من هنا، idempotent حيث أمكن، وتسجّل في AuditLog."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from .models import AuditLog


@transaction.atomic
def record_audit(
    *,
    action: str,
    actor: AbstractBaseUser | None = None,
    target: str = "",
    payload: dict[str, Any] | None = None,
    request_id: str = "",
) -> AuditLog:
    """idempotent على (action, target, request_id) عندما يُمرَّر request_id."""
    if request_id:
        existing = AuditLog.objects.filter(action=action, target=target, request_id=request_id).first()
        if existing:
            return existing
    return AuditLog.objects.create(
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        target=target,
        payload=payload or {},
        request_id=request_id,
    )
