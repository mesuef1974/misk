"""كتابة الإنتاج: تخطيط الألواح وتسجيل التشغيل. كلاهما idempotent."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.catalog.models import Calibration, Material
from apps.core.services import record_audit
from apps.orders.models import Order, OrderItem

from . import domain
from .models import Placement, RunLog, Sheet

MARGIN_MM = Decimal("5")
GAP_MM = Decimal("3")
PLANNABLE = {Order.Status.CONFIRMED, Order.Status.IN_PRODUCTION}


class ProductionError(ValueError):
    """مخالفة لقاعدة عمل في الإنتاج."""


def _tenths(value: Decimal) -> int:
    return int((value * 10).to_integral_value())


def _mm(value: int) -> Decimal:
    return Decimal(value) / 10


@transaction.atomic
def plan_sheets(*, material_id: int, actor=None) -> list[Sheet]:
    """يرتّب على ألواح جديدة كل نسخ البنود المؤكَّدة من هذه المادة التي لم توضع بعد.

    إعادة الاستدعاء بلا بنود جديدة تعيد قائمة فارغة ولا تنشئ شيئًا.
    """
    material = Material.objects.get(pk=material_id)
    items = list(
        OrderItem.objects.select_for_update(of=("self",))
        .filter(material=material, order__status__in=PLANNABLE)
        .select_related("template")
        .prefetch_related("placements")
        .order_by("id")
    )
    pieces: list[domain.Piece] = []
    for item in items:
        done = {placement.copy_index for placement in item.placements.all()}
        width, height = _tenths(item.template.width_mm), _tenths(item.template.height_mm)
        pieces.extend(
            domain.Piece((item.pk, copy), width, height) for copy in range(item.quantity) if copy not in done
        )
    if not pieces:
        return []
    try:
        placed = domain.pack(
            pieces,
            sheet_width=_tenths(material.sheet_width_mm),
            sheet_height=_tenths(material.sheet_height_mm),
            margin=_tenths(MARGIN_MM),
            gap=_tenths(GAP_MM),
        )
    except domain.PackingError as exc:
        raise ProductionError(str(exc)) from exc

    sheets = Sheet.objects.bulk_create(
        Sheet(material=material, width_mm=material.sheet_width_mm, height_mm=material.sheet_height_mm)
        for _ in range(max(p.sheet for p in placed) + 1)
    )
    Placement.objects.bulk_create(
        Placement(
            sheet=sheets[p.sheet],
            order_item_id=p.key[0],
            copy_index=p.key[1],
            x_mm=_mm(p.x),
            y_mm=_mm(p.y),
            width_mm=_mm(p.width),
            height_mm=_mm(p.height),
        )
        for p in placed
    )
    record_audit(
        action="production.plan",
        actor=actor,
        target=f"material:{material.pk}",
        payload={"sheets": [sheet.pk for sheet in sheets], "pieces": len(placed)},
    )
    return sheets


@transaction.atomic
def release_order(*, order_id: int, actor=None) -> int:
    """يرفع قطع الطلب عن الألواح المخطَّطة ويعيد عددها. الألواح المنفَّذة لا تُمسّ: قُصّت قطعها فعلًا.

    اللوح الذي يفرغ يُحذف إن لم يُشغَّل قط، ويصير «تالفًا» إن كان عليه تشغيل فاشل (سجله محميّ ومادته استُهلكت).
    idempotent: الاستدعاء الثاني لا يجد قطعًا فلا يكتب شيئًا.
    """
    # استعلام فرعي لا join مع distinct: PostgreSQL يرفض FOR UPDATE مع DISTINCT.
    on_order = Placement.objects.filter(order_item__order_id=order_id).values("sheet_id")
    sheets = list(
        Sheet.objects.select_for_update().filter(status=Sheet.Status.PLANNED, pk__in=on_order).order_by("id")
    )
    if not sheets:
        return 0
    sheet_ids = [sheet.pk for sheet in sheets]
    released, _ = Placement.objects.filter(sheet_id__in=sheet_ids, order_item__order_id=order_id).delete()
    occupied = set(Placement.objects.filter(sheet_id__in=sheet_ids).values_list("sheet_id", flat=True))
    empty = [pk for pk in sheet_ids if pk not in occupied]
    ran = set(RunLog.objects.filter(sheet_id__in=empty).values_list("sheet_id", flat=True))
    scrapped = sorted(ran)
    deleted = [pk for pk in empty if pk not in ran]
    Sheet.objects.filter(pk__in=scrapped).update(status=Sheet.Status.SCRAPPED)
    Sheet.objects.filter(pk__in=deleted).delete()
    record_audit(
        action="production.release",
        actor=actor,
        target=f"order:{order_id}",
        payload={"pieces": released, "sheets": sheet_ids, "deleted": deleted, "scrapped": scrapped},
    )
    return released


@transaction.atomic
def record_run(
    *,
    sheet_id: int,
    request_id: str,
    duration_s: int,
    outcome: str,
    calibration_id: int | None = None,
    notes: str = "",
    actor=None,
) -> RunLog:
    """تسجيل مكرر بالـ request_id نفسه يعيد السجل الموجود. النجاح يغلق اللوح."""
    if not request_id:
        raise ProductionError("request_id مطلوب لمنع التسجيل المكرر")
    existing = RunLog.objects.filter(request_id=request_id).first()
    if existing:
        return existing
    sheet = Sheet.objects.select_for_update().select_related("material").get(pk=sheet_id)
    if sheet.status != Sheet.Status.PLANNED:
        raise ProductionError(f"اللوح {sheet.pk} ليس مخطَّطًا ({sheet.get_status_display()})")
    calibration = None
    snapshot: dict[str, object] = {}
    if calibration_id is not None:
        calibration = Calibration.objects.get(pk=calibration_id)
        if calibration.material_id != sheet.material_id:
            raise ProductionError("المعايرة لمادة غير مادة اللوح")
        snapshot = {
            "operation": calibration.operation,
            "power_pct": calibration.power_pct,
            "speed_mm_s": str(calibration.speed_mm_s),
            "passes": calibration.passes,
            "lines_per_cm": calibration.lines_per_cm,
        }
    run = RunLog(
        sheet=sheet,
        calibration=calibration,
        settings_snapshot=snapshot,
        duration_s=duration_s,
        material_cost=sheet.material.sheet_cost,
        outcome=outcome,
        notes=notes,
        request_id=request_id,
    )
    run.full_clean()
    run.save()
    if outcome == RunLog.Outcome.OK:
        sheet.status = Sheet.Status.DONE
        sheet.save(update_fields=["status", "updated_at"])
    record_audit(
        action="production.run", actor=actor, target=f"sheet:{sheet.pk}", payload={"outcome": outcome}
    )
    return run
