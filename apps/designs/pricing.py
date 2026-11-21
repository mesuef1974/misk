"""سعر بيع نسخة على مادة. نقي: أرقام تدخل ورقم يخرج (docs/ready-designs-plan.md).

(تكلفة المادة + دقائق الماكينة × أجرة الدقيقة + أجرة التجميع) × (1 + الهامش٪)، مقرَّبًا إلى أعلى لأقرب `round_to`.
السعر اليدوي يغلب المعادلة. تقدير ناقص بلا سعر يدوي لا سعر له: زمنه أقل من الحقيقي فسعره كذلك.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Rates:
    minute_rate: Decimal
    margin_pct: Decimal
    round_to: Decimal


def price(
    *,
    rates: Rates | None,
    material_cost: Decimal,
    total_seconds: Decimal,
    complete: bool,
    assembly_fee: Decimal,
    manual_price: Decimal | None = None,
) -> Decimal | None:
    if rates is None:
        return None
    if manual_price is not None:
        return manual_price.quantize(CENT, rounding=ROUND_HALF_UP)
    if not complete:
        return None
    cost = material_cost + total_seconds / 60 * rates.minute_rate + assembly_fee
    raw = cost * (1 + rates.margin_pct / 100)
    steps = (raw / rates.round_to).to_integral_value(rounding=ROUND_CEILING)
    return (steps * rates.round_to).quantize(CENT, rounding=ROUND_HALF_UP)
