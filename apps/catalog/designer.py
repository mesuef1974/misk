"""المصمِّم: من قالب وخامة وقيم حقول إلى ملف واحد هو المعاينة وهو ملف القص (القسم 6 من المواصفات).

قراءة وحساب بلا كتابة. الخطأ يُمنع هنا قبل الدفع: حقول المخطط، ثم النص المسيء والديني، ثم أصغر خط
تحفره الخامة بوضوح (`Calibration.min_line_mm`) مقيسًا على النص بعد تحجيمه في خانته.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from django.core.cache import cache

from . import domain, generators, selectors, text_policy, typeset
from .models import Material, ProductTemplate

PREVIEW_CACHE_S = 10 * 60
# ارتفاع سطر عربي بحروفه الصاعدة والنازلة نسبةً إلى الإم (مقيس على الخطين: 1.20 و1.29).
LINE_HEIGHT_EM = 1.3


class DesignRejectedError(Exception):
    """رفض بسبب القيم. `errors`: {الحقل: رمز الخطأ}. `suggestions`: قوالب تسمح بالنص الديني."""

    def __init__(self, errors: dict[str, str], suggestions: list[str] | None = None):
        super().__init__("; ".join(f"{key}: {code}" for key, code in errors.items()))
        self.errors = errors
        self.suggestions = suggestions or []


class DesignUnavailableError(Exception):
    """القالب بلا مولّد، أو الخامة لا تُعرض عليه. `code` رمز السبب."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FieldLimit:
    field: str
    # قيم حقول الاختيار التي حُسب عندها الحدّ (النمط والخط).
    when: dict[str, Any]
    max_chars: int
    min_text_height_mm: float


@dataclass(frozen=True)
class Rendered:
    svg: str
    sha256: str
    width_mm: float
    height_mm: float
    needs_review: bool
    review_reasons: list[str] = field(default_factory=list)
    # مقاس الإم الناتج لكل حقل نص بالمليمتر.
    text_sizes: dict[str, float] = field(default_factory=dict)


def _generator(template: ProductTemplate) -> generators.Generator:
    try:
        return generators.GENERATORS[template.generator]
    except KeyError as exc:
        raise DesignUnavailableError("no_generator") from exc


def _dims(template: ProductTemplate, material: Material) -> generators.Dims:
    if not selectors.storefront_materials(template).filter(pk=material.pk).exists():
        raise DesignUnavailableError("material_not_offered")
    calibration = selectors.engrave_calibration(material.pk)
    if calibration is None:  # لا يقع بعد الفحص أعلاه؛ يحمي من سباق حذف المعايرة.
        raise DesignUnavailableError("material_not_offered")
    return generators.Dims(
        width=float(template.width_mm),
        height=float(template.height_mm),
        margin=float(template.safe_margin_mm),
        min_line=float(calibration.min_line_mm),
    )


def _font_key(params: dict[str, Any]) -> str:
    return generators.FONT_CHOICES.get(params.get(generators.FONT_FIELD, ""), typeset.DEFAULT_FONT)


def _text_fields(template: ProductTemplate) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in template.param_schema if f["type"] == "text"}


def limits(template: ProductTemplate, material: Material) -> list[FieldLimit]:
    """أقصى عدد حروف وأصغر ارتفاع نص لكل حقل، عند كل تركيبة من حقول الاختيار.

    الحدّ تقديري من متوسط عرض الحرف (للعدّاد في الواجهة)؛ الحكم القاطع في `render` على النص نفسه.
    """
    gen = _generator(template)
    dims = _dims(template, material)
    text_fields = _text_fields(template)
    choice_fields = [f for f in template.param_schema if f["type"] == "choice"]
    # الحقول العددية بأصغر قيمها: القطعة الأصغر تحدّ النص أكثر.
    base = {f["name"]: f["min"] for f in template.param_schema if f["type"] == "int" and "min" in f}
    result: list[FieldLimit] = []
    for combo in itertools.product(*(f["choices"] for f in choice_fields)):
        when = {f["name"]: value for f, value in zip(choice_fields, combo, strict=True)}
        font = _font_key(when)
        min_em = dims.min_line / typeset.stroke_em(font)
        for slot in gen.slots(dims, {**base, **when}):
            if slot.field not in text_fields:
                continue
            fits_height = min_em * LINE_HEIGHT_EM <= slot.max_h
            count = math.floor(slot.max_w / (min_em * typeset.mean_advance_em(font))) if fits_height else 0
            declared = int(text_fields[slot.field].get("max_length", domain.DEFAULT_TEXT_LENGTH))
            result.append(
                FieldLimit(
                    field=slot.field,
                    when=when,
                    max_chars=max(0, min(count, declared, slot.max_chars or declared)),
                    min_text_height_mm=round(min_em, 2),
                )
            )
    return result


def _policy(template: ProductTemplate, params: dict[str, Any]) -> list[str]:
    """يرفض المسيء والديني على قالب لا يسمح؛ ويعيد أسباب المراجعة اليدوية لما يُقبل."""
    errors: dict[str, str] = {}
    reasons: set[str] = set()
    for name in _text_fields(template):
        value = params.get(name)
        if not value:
            continue
        verdict = text_policy.inspect(value)
        if verdict.offensive:
            errors[name] = "offensive"
        elif verdict.religious and not template.allows_religious_text:
            errors[name] = "religious_not_allowed"
        elif verdict.religious:
            reasons.add("religious_text")
        elif verdict.divine_name:
            reasons.add("divine_name")
    if errors:
        suggestions = (
            list(selectors.religious_templates().exclude(pk=template.pk).values_list("slug", flat=True))
            if "religious_not_allowed" in errors.values()
            else []
        )
        raise DesignRejectedError(errors, suggestions)
    return sorted(reasons)


def _draw(template: ProductTemplate, dims: generators.Dims, params: dict[str, Any]) -> dict[str, Any]:
    gen = _generator(template)
    font = _font_key(params)
    stroke = typeset.stroke_em(font)
    errors: dict[str, str] = {}
    texts, sizes = {}, {}
    for slot in gen.slots(dims, params):
        value = params.get(slot.field)
        if not value:
            continue
        try:
            shape = typeset.outline(str(value), font)
        except typeset.TypesetError:
            errors[slot.field] = "unsupported_char"
            continue
        texts[slot.field], em_mm = typeset.fit(shape, slot.cx, slot.cy, slot.max_w, slot.max_h)
        if em_mm * stroke < dims.min_line:
            errors[slot.field] = "too_small"
        sizes[slot.field] = round(em_mm, 2)
    if errors:
        raise DesignRejectedError(errors)
    drawing = gen.draw(dims, params, texts)
    svg = generators.to_svg(drawing)
    return {
        "svg": svg,
        "sha256": hashlib.sha256(svg.encode()).hexdigest(),
        "width_mm": round(drawing.width, 2),
        "height_mm": round(drawing.height, 2),
        "text_sizes": sizes,
    }


def render(template: ProductTemplate, material: Material, params: Any) -> Rendered:
    """يرمي `domain.ParamError` لحقول المخطط، و`DesignRejectedError` للنص، و`DesignUnavailableError` للقالب والخامة."""
    gen = _generator(template)
    dims = _dims(template, material)
    cleaned = domain.clean_params(template.param_schema, params)
    if errors := gen.check(cleaned):
        raise DesignRejectedError(errors)
    reasons = _policy(template, cleaned)

    # الرسم نفسه يُحفظ دقائق: العميل يعيد الطلب نفسه وهو يقلّب الخيارات، والناتج حتمي من هذه المدخلات.
    fingerprint = json.dumps(
        [template.pk, template.updated_at.isoformat(), material.pk, asdict(dims), cleaned],
        ensure_ascii=False,
        sort_keys=True,
    )
    key = "designer:" + hashlib.sha256(fingerprint.encode()).hexdigest()
    drawn = cache.get(key)
    if drawn is None:
        drawn = _draw(template, dims, cleaned)
        cache.set(key, drawn, PREVIEW_CACHE_S)
    return Rendered(needs_review=bool(reasons), review_reasons=reasons, **drawn)
