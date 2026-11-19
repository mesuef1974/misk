"""طبقة القراءة (Selectors): استعلامات فقط، بلا آثار جانبية، مع select_related لتجنّب N+1."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import AuditLog


def recent_audit(limit: int = 50) -> QuerySet[AuditLog]:
    return AuditLog.objects.select_related("actor").order_by("-created_at")[:limit]


def audit_entries(*, action: str, target: str, request_id: str) -> list[AuditLog]:
    """الأحداث المسجَّلة بمفتاح idempotency هذا وبمفاتيحه الفرعية (`<المفتاح>+<لاحقة>`)، بترتيب تسجيلها.

    المفتاح الفرعي لعملية أُعيدت بالمفتاح نفسه فكتبت شيئًا جديدًا: صفّ ثانٍ لا يصطدم بقيد التفرّد.
    `request_id` فارغ لا يُطابق شيئًا.
    """
    if not request_id:
        return []
    keyed = Q(request_id=request_id) | Q(request_id__startswith=f"{request_id}+")
    return list(AuditLog.objects.filter(keyed, action=action, target=target).order_by("id"))
