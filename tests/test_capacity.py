import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.capacity import domain, selectors, services
from apps.capacity.models import CapacityConfig, Closure, DailyCapacity, OperatingWindow
from apps.catalog import services as catalog_services
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.production.models import Placement, RunLog, Sheet

QATAR = ZoneInfo("Asia/Qatar")
DOHA = {"latitude": 25.2854, "longitude": 51.5310, "utc_offset_h": 3}
SATURDAY = date(2026, 11, 21)  # نافذته 08:00–22:00
SUNDAY = date(2026, 11, 22)  # نافذته 14:00–22:00


def _hm(minutes: float) -> str:
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=QATAR)


def _order(material, quantity=1, status="confirmed"):
    order = order_services.create_order(
        client_ref=uuid.uuid4(),
        customer_name="زبون",
        items=[
            order_services.ItemInput(
                template_slug="name-tag", material_id=material.pk, params={"text": "نور"}, quantity=quantity
            )
        ],
    )
    Order.objects.filter(pk=order.pk).update(status=status)
    return order


# ---- المجال ----


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        # قيم مرجعية من الحساب نفسه (اختبار ثبات)؛ تُطابَق بجدول تقويم قطر الرسمي قبل الإطلاق.
        (date(2026, 11, 21), {"fajr": "04:35", "dhuhr": "11:19", "asr": "14:23", "maghrib": "16:44"}),
        (date(2026, 6, 21), {"fajr": "03:14", "dhuhr": "11:35", "asr": "14:58", "maghrib": "18:27"}),
    ],
)
def test_prayer_times_for_doha(day, expected):
    prayers = domain.prayer_minutes(day, **DOHA)
    for name, clock in expected.items():
        hours, minutes = map(int, clock.split(":"))
        assert abs(prayers[name] - (hours * 60 + minutes)) <= 2, (name, _hm(prayers[name]))
    assert prayers["isha"] - prayers["maghrib"] == pytest.approx(90)
    assert list(prayers) == list(domain.PRAYERS)


def test_open_minutes_subtracts_only_breaks_inside_window():
    assert domain.open_minutes(840, 1320, []) == 480
    # توقف قبل النافذة، وتوقف يقطع بدايتها، وتوقفان متداخلان داخلها.
    breaks = [(700, 725), (830, 850), (1000, 1025), (1010, 1040)]
    assert domain.open_minutes(840, 1320, breaks) == 480 - 10 - 40
    assert domain.open_minutes(900, 900, []) == 0
    assert domain.machine_minutes(431.9, 50) == 215


def test_friday_dhuhr_break_is_longer():
    prayers = {"fajr": 275.0, "dhuhr": 680.0, "asr": 860.0, "maghrib": 1000.0, "isha": 1090.0}
    friday = domain.prayer_breaks(prayers, weekday=domain.FRIDAY, break_min=25, friday_break_min=60)
    sunday = domain.prayer_breaks(prayers, weekday=6, break_min=25, friday_break_min=60)
    assert (680.0, 740.0) in friday and (860.0, 885.0) in friday
    assert (680.0, 705.0) in sunday


def test_piece_seconds_from_calibration():
    engrave = domain.Pass(speed_mm_s=200, passes=1, lines_per_cm=100)
    cut = domain.Pass(speed_mm_s=10, passes=2)
    common = {"width_mm": 80, "height_mm": 50, "margin_mm": 3, "fill_pct": 60, "handling_s": 60}
    # مساحة آمنة 74 × 44: 440 سطرًا × 74 مم ÷ 200 مم/ث × 60% = 97.68 ث، ثم المناولة.
    assert domain.piece_seconds(engrave=engrave, cut=None, **common) == pytest.approx(97.68 + 60)
    # القص: محيط 260 مم ÷ 10 مم/ث × مرّتان = 52 ث.
    assert domain.piece_seconds(engrave=engrave, cut=cut, **common) == pytest.approx(97.68 + 52 + 60)
    assert domain.piece_seconds(engrave=None, cut=cut, **common) is None


def test_allocate_fills_days_in_order_and_reports_overflow():
    days = [(SATURDAY, 100), (SUNDAY, 0), (SUNDAY + timedelta(days=1), 50)]
    loads, overflow = domain.allocate(days, [70, 60])
    assert [(load.booked_min, load.free_min) for load in loads] == [(100, 0), (0, 0), (30, 20)]
    assert overflow == 0
    assert domain.allocate(days, [200])[1] == 50


def test_finish_day_accumulates_free_minutes():
    free = [(SATURDAY, 0), (SUNDAY, 40), (SUNDAY + timedelta(days=1), 100)]
    assert domain.finish_day(free, 30) == SUNDAY
    assert domain.finish_day(free, 41) == SUNDAY + timedelta(days=1)
    assert domain.finish_day(free, 141) is None


# ---- السعة اليومية ----


@pytest.mark.django_db
def test_defaults_are_seeded():
    assert CapacityConfig.objects.get(pk=1).machine_ratio_pct == 50
    windows = {w.weekday: (w.opens, w.closes) for w in OperatingWindow.objects.all()}
    assert len(windows) == 7
    assert windows[4] == windows[5] == (time(8), time(22))
    assert windows[6] == (time(14), time(22))


@pytest.mark.django_db
def test_day_capacity_subtracts_prayers_and_applies_ratio():
    (_, sunday), (_, monday) = selectors.day_capacities(SUNDAY, 2)
    # 14:00–22:00 = 480 د، فيها العصر والمغرب والعشاء (25 د لكل منها): 405 د حضور، نصفها للماكينة.
    assert sunday == monday == 202
    # السبت 08:00–22:00 = 840 د، فيه الظهر أيضًا: 740 د.
    assert selectors.day_capacities(SATURDAY, 1)[0][1] == 370


@pytest.mark.django_db
def test_day_capacity_respects_closures_missing_windows_and_now():
    Closure.objects.create(start_date=SUNDAY, end_date=SUNDAY, reason="عيد")
    OperatingWindow.objects.filter(weekday=0).delete()
    capacities = dict(selectors.day_capacities(SATURDAY, 3))
    assert capacities[SUNDAY] == 0
    assert capacities[SUNDAY + timedelta(days=1)] == 0
    # السبت 20:00: بقيت ساعتان بلا صلاة = 120 د حضور.
    assert selectors.day_capacities(SATURDAY, 1, now=_at(SATURDAY, 20))[0][1] == 60
    assert selectors.day_capacities(SATURDAY, 1, now=_at(SATURDAY, 23))[0][1] == 0


# ---- الطابور والملخص ----


@pytest.mark.django_db
def test_order_minutes_uses_calibration_or_fallback(material, name_tag, calibration):
    order = _order(material, quantity=30)
    # ميدالية 80 × 50 بهامش 3: 440 سطرًا افتراضيًّا × 74 ÷ 200 × 60% + 60 = 157.68 ث للقطعة.
    assert selectors.order_minutes(order.pk) == 79  # ceil(30 × 157.68 ÷ 60)
    calibration.delete()
    assert selectors.order_minutes(order.pk) == 300  # 30 × 10 د بلا معايرة حفر


@pytest.mark.django_db
def test_backlog_counts_load_statuses_and_drops_cut_pieces(material, name_tag, calibration):
    first = _order(material, quantity=30)
    _order(material, quantity=30, status="draft")
    _order(material, quantity=30, status="delivered")
    _order(material, quantity=10, status="paid")
    assert selectors.backlog_minutes() == [79, 27]
    sheet = Sheet.objects.create(material=material, width_mm=600, height_mm=305, status=Sheet.Status.DONE)
    item = first.items.get()
    for copy in range(20):
        Placement.objects.create(
            sheet=sheet, order_item=item, copy_index=copy, x_mm=0, y_mm=0, width_mm=80, height_mm=50
        )
    assert selectors.backlog_minutes() == [27, 27]  # بقيت 10 قطع من الأول


@pytest.mark.django_db
def test_correction_factor_follows_run_log(material, name_tag, calibration):
    assert selectors.correction_factor() == 1.0
    order = _order(material, quantity=10)
    sheet = Sheet.objects.create(material=material, width_mm=600, height_mm=305, status=Sheet.Status.DONE)
    for copy in range(10):
        Placement.objects.create(
            sheet=sheet,
            order_item=order.items.get(),
            copy_index=copy,
            x_mm=0,
            y_mm=0,
            width_mm=80,
            height_mm=50,
        )
    # المقدَّر 10 × 157.68 = 1576.8 ث، والفعلي ضعفه.
    RunLog.objects.create(sheet=sheet, duration_s=3154, outcome="ok", request_id="r1")
    assert selectors.correction_factor() == pytest.approx(2.0, abs=0.01)
    RunLog.objects.create(sheet=sheet, duration_s=99999, outcome="ok", request_id="r2")
    assert selectors.correction_factor() == 3.0  # محدود


@pytest.mark.django_db
def test_refresh_summary_books_backlog_and_is_idempotent(material, name_tag, calibration):
    _order(material, quantity=100)  # ceil(100 × 157.68 ÷ 60) = 263 د
    now = _at(SATURDAY, 7)
    assert services.refresh_summary(now=now) == 0
    assert services.refresh_summary(now=now) == 0
    rows = list(DailyCapacity.objects.all())
    assert len(rows) == selectors.HORIZON_DAYS
    assert (rows[0].day, rows[0].capacity_min, rows[0].booked_min) == (SATURDAY, 370, 263)
    assert rows[1].booked_min == 0
    # اليوم التالي: صف الأمس يُحذف والأفق يتقدم.
    services.refresh_summary(now=_at(SUNDAY, 7))
    assert DailyCapacity.objects.count() == selectors.HORIZON_DAYS
    assert DailyCapacity.objects.first().day == SUNDAY


@pytest.mark.django_db
def test_earliest_ready_follows_queue_and_time_of_day(material, name_tag, calibration):
    _order(material, quantity=100)  # 263 د من 370 يوم السبت
    services.refresh_summary(now=_at(SATURDAY, 7))
    assert selectors.earliest_ready(100, now=_at(SATURDAY, 7)) == SATURDAY  # بقي 107 د
    assert selectors.earliest_ready(108, now=_at(SATURDAY, 7)) == SUNDAY
    # السبت 20:00: بقي من النافذة 60 د ماكينة فقط.
    assert selectors.earliest_ready(100, now=_at(SATURDAY, 20)) == SUNDAY
    assert selectors.earliest_ready(10**7, now=_at(SATURDAY, 7)) is None


@pytest.mark.django_db
def test_transition_refreshes_summary_after_commit(
    material, name_tag, calibration, django_capture_on_commit_callbacks
):
    order = _order(material, quantity=100, status="draft")
    services.refresh_summary()
    assert not DailyCapacity.objects.filter(booked_min__gt=0).exists()
    with django_capture_on_commit_callbacks(execute=True):
        order_services.transition(order_id=order.pk, to_status="confirmed")
    assert DailyCapacity.objects.filter(booked_min__gt=0).exists()


# ---- المسارات ----


@pytest.mark.django_db
def test_capacity_api(client, staff_user, material, name_tag, calibration):
    assert client.get("/api/capacity/days").status_code == 401
    client.force_login(staff_user)
    days = client.get("/api/capacity/days?days=7").json()  # أول نداء يبني الملخص
    assert len(days) == 7
    assert set(days[0]) == {"day", "capacity_min", "booked_min"}
    assert client.get("/api/capacity/days?days=999").status_code == 422
    assert client.get("/api/capacity/earliest?minutes=0").status_code == 422
    data = client.get("/api/capacity/earliest?minutes=60").json()
    assert data["minutes"] == 60 and data["ready_on"] >= days[0]["day"]
    order = _order(material, quantity=30, status="draft")
    assert client.get(f"/api/capacity/orders/{order.pk}/earliest").json()["minutes"] == 79
    assert client.get("/api/capacity/orders/999999/earliest").status_code == 404


@pytest.mark.django_db
def test_stale_summary_is_refreshed(client, staff_user, django_capture_on_commit_callbacks):
    client.force_login(staff_user)
    services.refresh_summary()
    yesterday = datetime.now(tz=QATAR) - timedelta(days=1)
    DailyCapacity.objects.update(updated_at=yesterday)
    assert selectors.summary_state(datetime.now(tz=QATAR).date()) == "stale"
    with django_capture_on_commit_callbacks(execute=True):
        assert client.get("/api/capacity/days?days=1").status_code == 200
    assert selectors.summary_state(datetime.now(tz=QATAR).date()) == "fresh"


@pytest.mark.django_db
def test_cut_calibration_adds_cut_time(material, name_tag, calibration):
    order = _order(material, quantity=30)
    catalog_services.record_calibration(
        material=material,
        operation="cut",
        power_pct=90,
        speed_mm_s=Decimal("10"),
        min_line_mm=Decimal("0.2"),
        measured_on=date(2026, 11, 16),
        passes=2,
    )
    assert selectors.order_minutes(order.pk) == 105  # ceil(30 × (157.68 + 52) ÷ 60)
