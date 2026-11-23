"""مسارات الإنتاج."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.http import HttpRequest
from ninja import Field, Query, Router, Schema, Status
from ninja.errors import HttpError

from apps.catalog.models import Calibration, Material
from apps.core.auth import request_id, staff_auth
from apps.core.paging import PageQuery, page_of
from apps.designs import selectors as design_selectors

from . import jobs, selectors, services
from .models import RunLog, Sheet

router = Router(tags=["الإنتاج"], auth=staff_auth)


class PlanIn(Schema):
    material_id: int


class PlacementOut(Schema):
    order_item_id: int
    order_id: int
    customer_name: str
    template_slug: str
    name: str
    variant_code: str  # غير فارغ لنسخة مسمّاة من تصميم جاهز
    cut_file_url: str  # ملف القص الجاهز لقطعة تصميم جاهز (للمشرفين)؛ فارغ لقطعة المصمِّم
    personalization: list[dict[str, str]]  # نص التخصيص الذي تضعه الورشة يدويًّا في الملف قبل القص: label وvalue
    copy_index: int
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal

    @staticmethod
    def resolve_order_id(obj) -> int:
        return obj.order_item.order_id

    @staticmethod
    def resolve_customer_name(obj) -> str:
        return obj.order_item.order.customer.name

    @staticmethod
    def resolve_template_slug(obj) -> str:
        return obj.order_item.template.slug

    @staticmethod
    def resolve_name(obj) -> str:
        return obj.order_item.template.name

    @staticmethod
    def resolve_variant_code(obj) -> str:
        variant = obj.order_item.design_variant
        return variant.code if variant else ""

    @staticmethod
    def resolve_personalization(obj) -> list[dict[str, str]]:
        item = obj.order_item
        if item.design_variant_id is None:
            return []
        labels = {field["name"]: field.get("label") or field["name"] for field in item.template.param_schema}
        return [{"label": labels.get(name, name), "value": str(value)} for name, value in item.params.items()]

    @staticmethod
    def resolve_cut_file_url(obj) -> str:
        variant = obj.order_item.design_variant
        if variant is None:
            return ""
        urls = design_selectors.cut_file_urls(variant)
        return urls[obj.copy_index % len(urls)]


class RunOut(Schema):
    id: int
    sheet_id: int
    outcome: str
    duration_s: int
    material_cost: Decimal
    notes: str
    created_at: datetime


class SheetOut(Schema):
    id: int
    material_id: int
    width_mm: Decimal
    height_mm: Decimal
    status: str
    placements: list[PlacementOut]
    runs: list[RunOut]  # الأحدث أولًا


class SheetPage(Schema):
    items: list[SheetOut]
    count: int  # كل ما يطابق التصفية، لا طول هذه الصفحة
    counts: dict[str, int]  # عدد الألواح لكل حالة في الجدول كله


class RunIn(Schema):
    duration_s: int = Field(ge=0, le=services.MAX_DURATION_S)
    outcome: str
    calibration_id: int | None = None
    notes: str = Field("", max_length=2000)


@router.get("/sheets", response=SheetPage)
def list_sheets(request: HttpRequest, page: Query[PageQuery], status: str | None = None):
    return page_of(selectors.sheets(status), page, selectors.status_counts(), status)


class PlanJobOut(Schema):
    id: str  # فارغ في التنفيذ المتزامن: لا شيء يُستطلع
    status: str  # pending | done | failed
    sheets: list[SheetOut]
    error: str = ""
    waiting: int = 0  # ألواح المادة المخطَّطة التي لم تُقصّ بعد التخطيط


def _job_out(job: jobs.PlanJob) -> dict:
    sheets = selectors.sheets().filter(pk__in=job.sheet_ids) if job.sheet_ids else []
    return {"id": job.id, "status": job.status, "sheets": sheets, "error": job.error, "waiting": job.waiting}


@router.post("/sheets/plan", response={200: PlanJobOut, 202: PlanJobOut})
def plan(request: HttpRequest, payload: PlanIn):
    """200 بالألواح حين يُخطَّط في الطلب نفسه، و202 بمعرّف يُستطلع من `/sheets/plan/{id}` حين يُخطَّط في العامل."""
    try:
        job = jobs.start_plan(material_id=payload.material_id, actor=request.user)
    except Material.DoesNotExist as exc:
        raise HttpError(404, "المادة غير موجودة") from exc
    except services.ProductionError as exc:
        raise HttpError(422, str(exc)) from exc
    return Status(202 if job.status == jobs.PENDING else 200, _job_out(job))


@router.get("/sheets/plan/{job_id}", response=PlanJobOut)
def plan_status(request: HttpRequest, job_id: str):
    job = jobs.plan_job(job_id)
    if job is None:
        raise HttpError(404, "مهمة تخطيط غير معروفة")
    return _job_out(job)


@router.post("/sheets/{sheet_id}/runs", response=RunOut)
def record_run(request: HttpRequest, sheet_id: int, payload: RunIn):
    if payload.outcome not in RunLog.Outcome.values:
        raise HttpError(422, "نتيجة غير معروفة")
    if len(request_id(request)) > services.REQUEST_ID_LENGTH:
        raise HttpError(422, f"X-Request-ID أطول من {services.REQUEST_ID_LENGTH} حرفًا")
    try:
        return services.record_run(
            sheet_id=sheet_id, request_id=request_id(request), actor=request.user, **payload.dict()
        )
    except (Sheet.DoesNotExist, Calibration.DoesNotExist) as exc:
        raise HttpError(404, "اللوح أو المعايرة غير موجودة") from exc
    except services.ProductionError as exc:
        raise HttpError(409, str(exc)) from exc


@router.post("/sheets/{sheet_id}/scrap", response=SheetOut)
def scrap(request: HttpRequest, sheet_id: int):
    try:
        services.scrap_sheet(sheet_id=sheet_id, actor=request.user)
    except Sheet.DoesNotExist as exc:
        raise HttpError(404, "اللوح غير موجود") from exc
    except services.ProductionError as exc:
        raise HttpError(409, str(exc)) from exc
    return selectors.sheets().get(pk=sheet_id)
