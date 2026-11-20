"""تقدير زمن الماكينة وتكلفة المادة لنسخة على مادة. نقي: يأخذ نتيجة التحليل وأرقام المعايرة ويعيد أرقامًا.

القص والعلام: الطول ÷ السرعة × المرات. الحفر النقطي: (مساحة الإحاطة ÷ تباعد الأسطر) ÷ السرعة × المرات،
والتباعد 10 ÷ أسطر السنتيمتر. الزمن لا يشمل تنقّل الرأس. عملية بلا معايرة تبقى `None` فلا يبدو الزمن كاملًا وهو ناقص.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Setting:
    speed_mm_s: Decimal
    passes: int
    lines_per_cm: int | None
    calibration_id: int


@dataclass(frozen=True)
class Estimate:
    seconds: dict[str, float | None]
    total_seconds: Decimal
    complete: bool
    material_area_mm2: Decimal
    material_cost: Decimal
    calibration_ids: list[int]


def _operation_seconds(group: dict, setting: Setting | None) -> float | None:
    if setting is None:
        return None
    speed = float(setting.speed_mm_s)
    if group["operation"] == "engrave":
        if not setting.lines_per_cm:
            return None
        spacing_mm = 10 / setting.lines_per_cm
        return group["bbox_area_mm2"] / spacing_mm / speed * setting.passes
    return group["length_mm"] / speed * setting.passes


def estimate(
    *,
    operations: dict[str, dict],
    material_kind: str,
    settings: dict[str, Setting],
    material_area_mm2: float,
    sheet_area_mm2: Decimal,
    sheet_cost: Decimal,
) -> Estimate | None:
    """`None` إن لم يكن في النسخة عملية على نوع المادة هذا."""
    groups = [g for g in operations.values() if g["material"] == material_kind]
    if not groups:
        return None
    seconds: dict[str, float | None] = {}
    for group in groups:
        value = _operation_seconds(group, settings.get(group["operation"]))
        seconds[group["operation"]] = None if value is None else round(value, 1)
    known = [v for v in seconds.values() if v is not None]
    area = Decimal(str(round(material_area_mm2, 1)))
    cost = (area / sheet_area_mm2 * sheet_cost) if sheet_area_mm2 else Decimal("0")
    used = sorted({settings[g["operation"]].calibration_id for g in groups if g["operation"] in settings})
    return Estimate(
        seconds=seconds,
        total_seconds=Decimal(str(round(sum(known), 1))),
        complete=len(known) == len(seconds),
        material_area_mm2=area,
        material_cost=cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        calibration_ids=used,
    )
