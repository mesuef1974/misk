"""مهمة التخطيط كما يراها الطالب: تُنفَّذ في الطلب نفسه أو في عامل Celery بحسب `PLANNING_ASYNC`.

الشكل واحد في الحالين كي لا تفرّق الواجهة: `done` بألواحه، أو `pending` بمعرّف يُستطلع، أو `failed` برسالة.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from celery.result import AsyncResult
from django.conf import settings

from apps.catalog.models import Material

from . import services, tasks

PENDING, DONE, FAILED = "pending", "done", "failed"
WORKER_FAILED = "تعذّر التخطيط في الخلفية؛ أعد المحاولة"


@dataclass(frozen=True)
class PlanJob:
    id: str
    status: str
    sheet_ids: list[int] = field(default_factory=list)
    error: str = ""


def start_plan(*, material_id: int, actor=None) -> PlanJob:
    """يرمي `Material.DoesNotExist` فورًا في الحالين، و`ProductionError` في التنفيذ المتزامن وحده."""
    Material.objects.only("pk").get(pk=material_id)
    if not settings.PLANNING_ASYNC:
        sheets = services.plan_sheets(material_id=material_id, actor=actor)
        return PlanJob(id="", status=DONE, sheet_ids=[sheet.pk for sheet in sheets])
    result = tasks.plan_sheets_async.delay(material_id=material_id, actor_id=getattr(actor, "pk", None))
    return plan_job(result.id) or PlanJob(id=result.id, status=PENDING)


def plan_job(job_id: str) -> PlanJob | None:
    """`None` لمعرّف ليس UUID أو لمهمة ليست تخطيطًا. Celery لا يميّز المعرّف المجهول من المنتظر، فكلاهما `pending`؛ والواجهة تحدّ الاستطلاع."""
    try:
        job_id = str(uuid.UUID(job_id))
    except ValueError:
        return None
    result = AsyncResult(job_id, app=tasks.plan_sheets_async.app)
    # المعرّف يكتبه العميل، فقد يشير إلى مهمة أخرى: اسمها (إن حُفظ) وشكل نتيجتها يُفحصان قبل القراءة.
    if result.name not in (None, tasks.plan_sheets_async.name):
        return None
    if result.state == "FAILURE":
        return PlanJob(id=job_id, status=FAILED, error=WORKER_FAILED)
    if result.state != "SUCCESS":
        return PlanJob(id=job_id, status=PENDING)
    outcome = result.result
    if not isinstance(outcome, dict):
        return None
    error, sheet_ids = outcome.get("error"), outcome.get("sheets", [])
    if error:
        return PlanJob(id=job_id, status=FAILED, error=error) if isinstance(error, str) else None
    if not isinstance(sheet_ids, list) or not all(type(pk) is int for pk in sheet_ids):
        return None
    return PlanJob(id=job_id, status=DONE, sheet_ids=sheet_ids)
