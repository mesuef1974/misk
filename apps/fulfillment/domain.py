"""حساب مواعيد الاستلام وخطوات التتبّع. دوال خالصة بلا قاعدة بيانات. الدقائق من منتصف الليل المحلي."""

from __future__ import annotations

import math
from collections.abc import Iterable

MINUTES_PER_DAY = 24 * 60


def slot_starts(
    opens: float, closes: float, breaks: Iterable[tuple[float, float]], slot_min: int
) -> list[int]:
    """بدايات المواعيد في نافذة الحضور. موعد يمسّ توقف صلاة أو يتجاوز الإغلاق لا يُعرض."""
    if slot_min <= 0:
        return []
    pauses = list(breaks)
    closes = min(closes, MINUTES_PER_DAY)
    starts = []
    start = math.ceil(opens)
    while start + slot_min <= closes:
        end = start + slot_min
        if all(end <= pause_start or start >= pause_end for pause_start, pause_end in pauses):
            starts.append(start)
        start = end
    return starts


def steps(*, storefront: bool, fulfillment: str, reviewed: bool) -> list[str]:
    """خطوات الطلب كما يراها العميل، بالترتيب. الإلغاء والاسترداد حالتان ختاميتان لا خطوتان."""
    path = ["paid"] if storefront else []
    if reviewed:
        path.append("under_review")
    path += ["confirmed", "in_production", "ready"]
    if fulfillment == "pickup":
        path.append("ready_for_pickup")
    elif fulfillment == "delivery":
        path.append("out_for_delivery")
    path.append("delivered")
    return path
