"""مسارات الكتالوج. تستدعي الخدمات والمحدِّدات فقط."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.core.auth import staff_auth

from . import domain, selectors, services
from .models import Material

router = Router(tags=["الكتالوج"], auth=staff_auth)


class MaterialIn(Schema):
    name: str
    kind: str
    thickness_mm: Decimal
    sheet_cost: Decimal = Decimal("0")
    supplier: str = ""
    notes: str = ""


class MaterialOut(Schema):
    id: int
    name: str
    kind: str
    thickness_mm: Decimal
    sheet_width_mm: Decimal
    sheet_height_mm: Decimal
    sheet_cost: Decimal
    supplier: str
    notes: str


class CalibrationIn(Schema):
    operation: str
    power_pct: int
    speed_mm_s: Decimal
    min_line_mm: Decimal
    measured_on: date
    passes: int = 1
    lines_per_cm: int | None = None
    notes: str = ""


class CalibrationOut(Schema):
    id: int
    material_id: int
    operation: str
    power_pct: int
    speed_mm_s: Decimal
    passes: int
    lines_per_cm: int | None
    min_line_mm: Decimal
    measured_on: date
    notes: str


class TemplateIn(Schema):
    slug: str
    name: str
    generator: str
    width_mm: Decimal
    height_mm: Decimal
    param_schema: list[dict[str, Any]] = []
    base_price: Decimal = Decimal("0")


class TemplateOut(Schema):
    id: int
    slug: str
    name: str
    generator: str
    width_mm: Decimal
    height_mm: Decimal
    safe_margin_mm: Decimal
    param_schema: list[dict[str, Any]]
    base_price: Decimal


def _invalid(exc: Exception) -> HttpError:
    if isinstance(exc, domain.ParamError):
        return HttpError(422, str(exc))
    if isinstance(exc, ValidationError):
        return HttpError(422, "; ".join(exc.messages))
    return HttpError(422, str(exc))


@router.get("/materials", response=list[MaterialOut])
def list_materials(request: HttpRequest):
    return selectors.active_materials()


@router.post("/materials", response=MaterialOut)
def save_material(request: HttpRequest, payload: MaterialIn):
    try:
        return services.upsert_material(actor=request.user, **payload.dict())
    except ValidationError as exc:
        raise _invalid(exc) from exc


@router.get("/materials/{material_id}/calibrations", response=list[CalibrationOut])
def list_calibrations(request: HttpRequest, material_id: int):
    return selectors.calibrations_for(material_id)


@router.post("/materials/{material_id}/calibrations", response=CalibrationOut)
def add_calibration(request: HttpRequest, material_id: int, payload: CalibrationIn):
    material = get_object_or_404(Material, pk=material_id)
    try:
        return services.record_calibration(material=material, actor=request.user, **payload.dict())
    except ValidationError as exc:
        raise _invalid(exc) from exc


@router.get("/templates", response=list[TemplateOut])
def list_templates(request: HttpRequest):
    return selectors.active_templates()


@router.post("/templates", response=TemplateOut)
def save_template(request: HttpRequest, payload: TemplateIn):
    try:
        return services.upsert_template(actor=request.user, **payload.dict())
    except (domain.ParamError, ValidationError) as exc:
        raise _invalid(exc) from exc
