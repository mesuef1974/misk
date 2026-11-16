"""مسارات الإنتاج."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.http import HttpRequest
from ninja import Field, Query, Router, Schema
from ninja.errors import HttpError

from apps.catalog.models import Calibration, Material
from apps.core.auth import request_id, staff_auth
from apps.core.paging import PageQuery, page_of

from . import selectors, services
from .models import RunLog, Sheet

router = Router(tags=["الإنتاج"], auth=staff_auth)


class PlanIn(Schema):
    material_id: int


class PlacementOut(Schema):
    order_item_id: int
    order_id: int
    customer_name: str
    template_slug: str
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


@router.post("/sheets/plan", response=list[SheetOut])
def plan(request: HttpRequest, payload: PlanIn):
    try:
        planned = services.plan_sheets(material_id=payload.material_id, actor=request.user)
    except Material.DoesNotExist as exc:
        raise HttpError(404, "المادة غير موجودة") from exc
    except services.ProductionError as exc:
        raise HttpError(422, str(exc)) from exc
    return selectors.sheets().filter(pk__in=[sheet.pk for sheet in planned])


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
