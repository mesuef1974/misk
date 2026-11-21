"""حساب السعة: مواقيت الصلاة، دقائق الماكينة في اليوم، زمن القطعة، وتوزيع الطابور على الأيام.

دوال خالصة بلا قاعدة بيانات. الدقائق تُعدّ من منتصف الليل المحلي.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")
FRIDAY = 4  # date.weekday()

# طريقة تقويم قطر: الفجر عند انخفاض الشمس 18°، والعشاء بعد المغرب بـ 90 دقيقة، والعصر بظل المثل.
FAJR_ANGLE = 18.0
ISHA_AFTER_MAGHRIB_MIN = 90.0
ASR_SHADOW_FACTOR = 1.0
HORIZON_ANGLE = 0.833  # انكسار الضوء ونصف قطر قرص الشمس

DEFAULT_LINES_PER_CM = 100


def _sin(deg: float) -> float:
    return math.sin(math.radians(deg))


def _cos(deg: float) -> float:
    return math.cos(math.radians(deg))


def _sun(julian_day: float) -> tuple[float, float]:
    """ميل الشمس بالدرجات ومعادلة الزمن بالساعات (خوارزمية المرصد البحري الأمريكي المبسّطة، دقتها دون الدقيقة)."""
    d = julian_day - 2451545.0
    g = (357.529 + 0.98560028 * d) % 360
    q = (280.459 + 0.98564736 * d) % 360
    lam = (q + 1.915 * _sin(g) + 0.020 * _sin(2 * g)) % 360
    obliquity = 23.439 - 0.00000036 * d
    right_ascension = math.degrees(math.atan2(_cos(obliquity) * _sin(lam), _cos(lam))) / 15
    declination = math.degrees(math.asin(_sin(obliquity) * _sin(lam)))
    return declination, q / 15 - right_ascension % 24


def prayer_minutes(day: date, *, latitude: float, longitude: float, utc_offset_h: float) -> dict[str, float]:
    """مواقيت اليوم بالدقائق من منتصف الليل المحلي."""
    julian_midnight = day.toordinal() + 1721424.5 - longitude / 360

    def midday(guess_h: float) -> tuple[float, float]:
        declination, equation = _sun(julian_midnight + guess_h / 24)
        return (12 - equation) % 24, declination

    def hour_angle(sun_altitude: float, declination: float) -> float:
        cos_h = (_sin(sun_altitude) - _sin(latitude) * _sin(declination)) / (
            _cos(latitude) * _cos(declination)
        )
        return math.degrees(math.acos(max(-1.0, min(1.0, cos_h)))) / 15

    def at(guess_h: float, sun_altitude: float | None, sign: int) -> float:
        noon, declination = midday(guess_h)
        if sun_altitude is None:  # العصر: ارتفاع الشمس حين يساوي الظل طول الشاخص زائد ظل الزوال
            shadow = ASR_SHADOW_FACTOR + math.tan(math.radians(abs(latitude - declination)))
            sun_altitude = math.degrees(math.atan(1 / shadow))
        return noon + sign * hour_angle(sun_altitude, declination)

    shift = utc_offset_h - longitude / 15  # من التوقيت الشمسي المحلي إلى توقيت المنطقة
    maghrib = at(18, -HORIZON_ANGLE, +1)
    hours = {
        "fajr": at(5, -FAJR_ANGLE, -1),
        "dhuhr": midday(12)[0],
        "asr": at(15, None, +1),
        "maghrib": maghrib,
        "isha": maghrib + ISHA_AFTER_MAGHRIB_MIN / 60,
    }
    return {name: (value + shift) * 60 for name, value in hours.items()}


def prayer_breaks(
    prayers: dict[str, float], *, weekday: int, break_min: int, friday_break_min: int
) -> list[tuple[float, float]]:
    """توقف لكل صلاة من الأذان؛ ظهر الجمعة بمدته الخاصة."""
    return [
        (start, start + (friday_break_min if weekday == FRIDAY and name == "dhuhr" else break_min))
        for name, start in prayers.items()
    ]


def open_minutes(opens: float, closes: float, breaks: Iterable[tuple[float, float]]) -> float:
    """دقائق الحضور في النافذة بعد طرح التوقفات (تُدمج إن تداخلت)."""
    if closes <= opens:
        return 0.0
    total = closes - opens
    cursor = opens
    for start, end in sorted(breaks):
        start, end = max(start, cursor), min(end, closes)
        if end > start:
            total -= end - start
            cursor = end
    return max(total, 0.0)


def machine_minutes(open_min: float, ratio_pct: int) -> int:
    """الليزر لا يعمل دون حضور، ولا يعمل الحضور كله: نسبة منه للماكينة."""
    return int(round(open_min * ratio_pct / 100, 6))  # التقريب يمحو خطأ الفاصلة العائمة قبل القطع


@dataclass(frozen=True)
class Pass:
    """إعدادات عملية من المعايرة."""

    speed_mm_s: float
    passes: int = 1
    lines_per_cm: int | None = None


def piece_seconds(
    *,
    width_mm: float,
    height_mm: float,
    margin_mm: float,
    engrave: Pass | None,
    cut: Pass | None,
    fill_pct: int,
    handling_s: int,
) -> float | None:
    """زمن قطعة واحدة: حفر نقطي للمساحة الآمنة بنسبة التغطية، وقص المحيط، ومناولة. `None` بلا معايرة حفر.

    الحفر النقطي يمسح أسطرًا بعرض العمل: عدد الأسطر = الارتفاع × الأسطر لكل مم، وكل سطر يُقطع بسرعة المعايرة.
    """
    if engrave is None:
        return None
    inner_w = max(width_mm - 2 * margin_mm, 0.0)
    inner_h = max(height_mm - 2 * margin_mm, 0.0)
    lines = inner_h * (engrave.lines_per_cm or DEFAULT_LINES_PER_CM) / 10
    seconds = lines * inner_w / engrave.speed_mm_s * engrave.passes * fill_pct / 100
    if cut is not None:
        seconds += 2 * (width_mm + height_mm) / cut.speed_mm_s * cut.passes
    return seconds + handling_s


@dataclass(frozen=True)
class DayLoad:
    day: date
    capacity_min: int
    booked_min: int

    @property
    def free_min(self) -> int:
        return self.capacity_min - self.booked_min


def allocate(days: Sequence[tuple[date, int]], jobs_min: Iterable[int]) -> tuple[list[DayLoad], int]:
    """يملأ الأيام بالطابور بالترتيب (الأقدم أولًا). يعيد حِمل كل يوم وما فاض عن الأفق بالدقائق."""
    remaining = sum(jobs_min)
    loads = []
    for day, capacity in days:
        booked = min(capacity, remaining)
        remaining -= booked
        loads.append(DayLoad(day, capacity, booked))
    return loads, remaining


def finish_day(free: Iterable[tuple[date, int]], minutes: int) -> date | None:
    """أول يوم تكتمل فيه `minutes` من السعة الحرة المتراكمة. `None` إن لم يتسع الأفق."""
    needed = max(minutes, 0)
    for day, free_min in free:
        needed -= max(free_min, 0)
        if needed <= 0 and free_min > 0:
            return day
    return None
