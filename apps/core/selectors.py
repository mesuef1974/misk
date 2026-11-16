"""طبقة القراءة (Selectors): استعلامات فقط، بلا آثار جانبية، مع select_related لتجنّب N+1."""

from __future__ import annotations

from django.db.models import QuerySet

from .models import AuditLog


def recent_audit(limit: int = 50) -> QuerySet[AuditLog]:
    return AuditLog.objects.select_related("actor").order_by("-created_at")[:limit]
