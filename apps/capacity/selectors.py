"""قراءة السعة: الإعداد، سعة اليوم، طابور الطلبات بالدقائق، وأقرب موعد جاهزية من الملخص."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.catalog.models import Calibration
from apps.orders.models import Order, OrderItem
from apps.production.models import Placement, RunLog, Sheet

from . import domain
from .models import CapacityConfig, Closure, DailyCapacity, OperatingWindow

# ما دُفع أو أُكِّد ولم يكتمل قصّه يحجز من السعة.
LOAD_STATUSES = (
    Order.Status.PAID,
    Order.Status.UNDER_REVIEW,
    Order.Status.CONFIRMED,
    Order.Status.IN_PRODUCTION,
)
HORIZON_DAYS = 180
CORRECTION_RUNS = 50
CORRECTION_BOUNDS = (0.5, 3.0)

Passes = dict[tuple[int, str], domain.Pass]


def config() -> CapacityConfig:
    return CapacityConfig.objects.filter(pk=1).first() or CapacityConfig(pk=1)


def _minutes(value: time) -> float:
    return value.hour * 60 + value.minute + value.second / 60


def _utc_offset_h(day: date) -> float:
    offset = datetime.combine(day, time(12), tzinfo=timezone.get_current_timezone()).utcoffset()
    return offset.total_seconds() / 3600 if offset else 0.0


def day_capacities(start: date, days: int, *, now: datetime | None = None) -> list[tuple[date, int]]:
    """دقائق الماكينة لكل يوم من `start`. `now` (محلي) يقصّ ما مضى من نافذة يومه."""
    cfg = config()
    windows = {window.weekday: window for window in OperatingWindow.objects.all()}
    end = start + timedelta(days=days - 1)
    closures = list(Closure.objects.filter(start_date__lte=end, end_date__gte=start))
    out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        window = windows.get(day.weekday())
        if window is None or any(c.start_date <= day <= c.end_date for c in closures):
            out.append((day, 0))
            continue
        opens = _minutes(window.opens)
        if now is not None and now.date() == day:
            opens = max(opens, _minutes(now.time()))
        prayers = domain.prayer_minutes(
            day,
            latitude=float(cfg.latitude),
            longitude=float(cfg.longitude),
            utc_offset_h=_utc_offset_h(day),
        )
        breaks = domain.prayer_breaks(
            prayers,
            weekday=day.weekday(),
            break_min=cfg.prayer_break_min,
            friday_break_min=cfg.friday_prayer_break_min,
        )
        open_min = domain.open_minutes(opens, _minutes(window.closes), breaks)
        out.append((day, domain.machine_minutes(open_min, cfg.machine_ratio_pct)))
    return out


def _passes(material_ids: set[int]) -> Passes:
    """أحدث معايرة لكل (مادة، عملية)."""
    latest: Passes = {}
    rows = Calibration.objects.filter(material_id__in=material_ids).order_by("measured_on", "id")
    for row in rows:  # الأحدث يكتب فوق الأقدم
        latest[(row.material_id, row.operation)] = domain.Pass(
            speed_mm_s=float(row.speed_mm_s), passes=row.passes, lines_per_cm=row.lines_per_cm
        )
    return latest


def _piece_seconds(item: OrderItem, passes: Passes, cfg: CapacityConfig) -> float:
    template = item.template
    seconds = domain.piece_seconds(
        width_mm=float(template.width_mm),
        height_mm=float(template.height_mm),
        margin_mm=float(template.safe_margin_mm),
        engrave=passes.get((item.material_id, Calibration.Operation.ENGRAVE)),
        cut=passes.get((item.material_id, Calibration.Operation.CUT)),
        fill_pct=cfg.engrave_fill_pct,
        handling_s=cfg.handling_s_per_piece,
    )
    return cfg.fallback_piece_min * 60 if seconds is None else seconds


def correction_factor() -> float:
    """نسبة الزمن الفعلي إلى المقدَّر في آخر التشغيلات الناجحة. 1 بلا سجل."""
    runs = list(
        RunLog.objects.filter(outcome=RunLog.Outcome.OK)
        .order_by("-created_at", "-id")
        .values_list("sheet_id", "duration_s")[:CORRECTION_RUNS]
    )
    if not runs:
        return 1.0
    sheet_ids = {sheet_id for sheet_id, _ in runs}
    pieces = _placed_pieces(Q(sheet_id__in=sheet_ids))
    items = list(OrderItem.objects.filter(pk__in=pieces).select_related("template"))
    cfg = config()
    passes = _passes({item.material_id for item in items})
    estimated = sum(_piece_seconds(item, passes, cfg) * pieces[item.pk] for item in items)
    if estimated <= 0:
        return 1.0
    low, high = CORRECTION_BOUNDS
    return min(max(sum(duration for _, duration in runs) / estimated, low), high)


def _placed_pieces(where: Q) -> dict[int, int]:
    """عدد القطع الموضوعة لكل بند، باستعلام واحد."""
    return dict(Placement.objects.filter(where).order_by().values_list("order_item_id").annotate(Count("id")))


def _orders_minutes(orders: QuerySet[Order], *, remaining_only: bool) -> dict[int, int]:
    """دقائق كل طلب من بنوده. `remaining_only` يطرح القطع المقصوصة على ألواح منفَّذة."""
    items = list(OrderItem.objects.filter(order__in=orders).select_related("template"))
    cut = (
        _placed_pieces(Q(order_item__order__in=orders, sheet__status=Sheet.Status.DONE))
        if remaining_only
        else {}
    )
    cfg = config()
    factor = correction_factor()
    passes = _passes({item.material_id for item in items})
    seconds: dict[int, float] = {}
    for item in items:
        pieces = max(item.quantity - cut.get(item.pk, 0), 0)
        seconds[item.order_id] = seconds.get(item.order_id, 0.0) + pieces * _piece_seconds(item, passes, cfg)
    return {order_id: math.ceil(total * factor / 60) for order_id, total in seconds.items()}


def order_minutes(order_id: int) -> int:
    """زمن الماكينة المقدَّر لطلب كامل بالدقائق."""
    return _orders_minutes(Order.objects.filter(pk=order_id), remaining_only=False).get(order_id, 0)


def backlog_minutes() -> list[int]:
    """دقائق ما بقي من كل طلب في الطابور، الأقدم أولًا."""
    orders = Order.objects.filter(status__in=LOAD_STATUSES)
    minutes = _orders_minutes(orders, remaining_only=True)
    order_ids = orders.order_by("created_at", "id").values_list("pk", flat=True)
    return [minutes.get(order_id, 0) for order_id in order_ids]


def summary(start: date, days: int) -> QuerySet[DailyCapacity]:
    return DailyCapacity.objects.filter(day__gte=start, day__lt=start + timedelta(days=days))


def summary_state(today: date) -> str:
    """`missing` بلا صف لليوم، `stale` إن حُسب قبل اليوم، وإلا `fresh`."""
    row = DailyCapacity.objects.filter(day=today).first()
    if row is None:
        return "missing"
    return "stale" if timezone.localtime(row.updated_at).date() < today else "fresh"


def earliest_ready(minutes: int, *, now: datetime) -> date | None:
    """أقرب يوم تكتمل فيه `minutes` بعد الطابور، من الملخص المحفوظ. ما مضى من نافذة اليوم لا يُعدّ."""
    today = now.date()
    left_today = day_capacities(today, 1, now=now)[0][1]
    free = []
    for row in DailyCapacity.objects.filter(day__gte=today):
        free_min = row.capacity_min - row.booked_min
        free.append((row.day, min(free_min, left_today) if row.day == today else free_min))
    return domain.finish_day(free, minutes)
