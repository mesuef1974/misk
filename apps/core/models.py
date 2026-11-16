"""نماذج نحيلة: حقول وقيود فقط. المنطق في services.py (Skinny Models / Fat Services)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(TimeStampedModel):
    """سجل تدقيق append-only (Audit Trail). لا يُحدَّث ولا يُحذف من الشيفرة."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # لقطة الاسم وقت الحدث: حذف المستخدم يُفرغ `actor` ولا يُفقد السجلَّ نسبتَه.
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "created_at"])]
        constraints = [
            # مفتاح idempotency: طلبان متزامنان بالـ request_id نفسه لا ينتجان صفّين.
            models.UniqueConstraint(
                fields=["action", "target", "request_id"],
                condition=~models.Q(request_id=""),
                name="uniq_audit_action_target_request",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.target}".strip()
