"""مولّدات القوالب: هندسة خالصة من أبعاد القالب وقيم الحقول إلى طبقات الحفر والقص.

المفتاح هو `ProductTemplate.generator`. كل مولّد يعلن خانات نصّه (`slots`) ثم يرسم (`draw`) بالنص بعد
تحجيمه في خاناته؛ فحدود الحروف والمعاينة وملف القص من هندسة واحدة. الوحدة مليمتر وy للأسفل.
طبقات xTool بالألوان: أسود تعبئة حفر، أحمر خط قص، أزرق متقطّع مرجع لا يُخرج.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

FONT_FIELD = "الخط"
# أسماء الخيار في مخطط القالب ومفاتيح `typeset.FONTS`. خيار قديم غير معروف يأخذ الخط الافتراضي.
FONT_CHOICES = {"كايرو": "cairo", "المراي": "almarai"}

ENGRAVE = 'fill="#000000" stroke="none"'
CUT = 'fill="none" stroke="#ff0000" stroke-width="0.1"'
GUIDE = 'fill="none" stroke="#0000ff" stroke-width="0.2" stroke-dasharray="1 1"'


@dataclass(frozen=True)
class Dims:
    width: float
    height: float
    margin: float
    # أصغر خط تحفره الخامة بوضوح: الزخارف لا تنزل عنه.
    min_line: float = 0.0


@dataclass(frozen=True)
class Slot:
    """خانة نص: الحقل، ومركزها، وأقصى عرض وارتفاع يُحجَّم النص داخلهما."""

    field: str
    cx: float
    cy: float
    max_w: float
    max_h: float
    # حدّ يفرضه التخطيط نفسه فوق حدّ الهندسة (حرفان في الدائرة).
    max_chars: int | None = None


@dataclass
class Drawing:
    width: float
    height: float
    engrave: BaseGeometry = field(default_factory=Polygon)
    cut: list[BaseGeometry] = field(default_factory=list)
    guide: list[BaseGeometry] = field(default_factory=list)


@dataclass(frozen=True)
class Generator:
    slots: Callable[[Dims, dict[str, Any]], list[Slot]]
    draw: Callable[[Dims, dict[str, Any], dict[str, BaseGeometry]], Drawing]
    # فحص قيم يتجاوز المخطط (مثل «حرفان» لا يزيد على حرفين). يعيد {الحقل: رمز الخطأ}.
    check: Callable[[dict[str, Any]], dict[str, str]] = lambda params: {}


def _line(width: float, dims: Dims) -> float:
    return max(width, dims.min_line)


def _ring(shape: BaseGeometry, width: float) -> BaseGeometry:
    return shape.difference(shape.buffer(-width))


# ---------- بطاقة مقوّسة ----------


def _card_slots(dims: Dims, params: dict[str, Any]) -> list[Slot]:
    w, h, m = dims.width, dims.height, dims.margin
    return [
        Slot("الاسم", w / 2, h * 0.45, w - 2 * (m + 4), h * 0.16),
        Slot("العبارة", w / 2, h * 0.66, w - 2 * (m + 8), h * 0.06),
    ]


def _card_draw(dims: Dims, params: dict[str, Any], texts: dict[str, BaseGeometry]) -> Drawing:
    w, h, r = dims.width, dims.height, dims.width / 2
    card = unary_union([Point(r, r).buffer(r, 64), box(0, r, w, h)])
    hole = Point(r, dims.margin + 5).buffer(2.0, 32)
    frame = _ring(card.buffer(-dims.margin), _line(0.6, dims))
    return Drawing(w, h, engrave=unary_union([frame, *texts.values()]), cut=[card, hole])


# ---------- ميدالية حرف ----------

_KEY_EDGE, _KEY_RING, _KEY_HOLE = 2.5, 5.0, 2.0


def _key_slots(dims: Dims, params: dict[str, Any]) -> list[Slot]:
    max_w = dims.width - 2 * _KEY_EDGE
    max_h = dims.height - 2 * _KEY_EDGE - (_KEY_RING + 3.0)
    return [Slot("الحرف", dims.width / 2, dims.height / 2, max_w, max_h, max_chars=1)]


def _bridge(shape: BaseGeometry, width: float) -> BaseGeometry:
    """يصل أجزاء الحرف المنفصلة (النقاط) بأقرب جزء، فتخرج قطعة قص واحدة."""
    parts = sorted(getattr(shape, "geoms", [shape]), key=lambda g: -g.area)
    joined = parts[0]
    for part in parts[1:]:
        a, b = nearest_points(joined, part)
        joined = unary_union([joined, part, LineString([a, b]).buffer(width / 2, 8)])
    return joined


def _key_draw(dims: Dims, params: dict[str, Any], texts: dict[str, BaseGeometry]) -> Drawing:
    glyph = texts["الحرف"]
    body = _bridge(glyph.buffer(_KEY_EDGE, 16), width=5.0)
    # الحلقة فوق أعلى نقطة في الجسم، فتتصل به دائمًا.
    top = min(body.exterior.coords, key=lambda p: p[1])
    center = Point(top[0], top[1] - 3.0)
    shape = unary_union([body, center.buffer(_KEY_RING, 32)])
    hole = center.buffer(_KEY_HOLE, 32)
    dx, dy = -shape.bounds[0], -shape.bounds[1]
    shape, glyph, hole = (affinity.translate(g, dx, dy) for g in (shape, glyph, hole))
    return Drawing(shape.bounds[2], shape.bounds[3], engrave=glyph, cut=[shape, hole])


def _key_check(params: dict[str, Any]) -> dict[str, str]:
    return {} if len(str(params.get("الحرف", "")).replace(" ", "")) == 1 else {"الحرف": "one_letter"}


# ---------- غطاء برطمان ----------


def _lid_diameter(dims: Dims, params: dict[str, Any]) -> float:
    return float(params.get("القطر مم") or dims.width)


def _lid_slots(dims: Dims, params: dict[str, Any]) -> list[Slot]:
    d = _lid_diameter(dims, params)
    return [Slot("الاسم", d / 2, d / 2, d - 20, d * 0.28)]


def _lid_draw(dims: Dims, params: dict[str, Any], texts: dict[str, BaseGeometry]) -> Drawing:
    d = _lid_diameter(dims, params)
    r = d / 2
    c = Point(r, r)
    outer = _ring(c.buffer(r - 3, 128), _line(0.8, dims))
    inner = _ring(c.buffer(r - 5, 128), _line(0.4, dims))
    dot = _line(0.7, dims) / 2
    dots = [
        Point(r + (r - 4.4) * math.cos(a), r + (r - 4.4) * math.sin(a)).buffer(dot, 8)
        for a in (2 * math.pi * i / 24 for i in range(24))
    ]
    engrave = unary_union([outer, inner, *dots, *texts.values()])
    return Drawing(d, d, engrave=engrave, guide=[c.buffer(r, 128)])


# ---------- كفر جلد ----------

_STYLE, _NAME_STYLE, _MONO_STYLE = "النمط", "اسم", "حرفان"


def _case_slots(dims: Dims, params: dict[str, Any]) -> list[Slot]:
    w, h = dims.width, dims.height
    if params.get(_STYLE) == _MONO_STYLE:
        return [Slot("النص", w / 2, h * 0.6, w * 0.27, w * 0.2, max_chars=2)]
    return [Slot("النص", w / 2, h * 0.64, w * 0.62, h * 0.13)]


def _case_draw(dims: Dims, params: dict[str, Any], texts: dict[str, BaseGeometry]) -> Drawing:
    w, h = dims.width, dims.height
    text = texts["النص"]
    if params.get(_STYLE) == _MONO_STYLE:
        c = Point(w / 2, h * 0.6)
        radius = w * 0.23
        extra: list[BaseGeometry] = [
            _ring(c.buffer(radius, 128), _line(0.8, dims)),
            _ring(c.buffer(radius - 2, 128), _line(0.3, dims)),
        ]
    else:
        y = text.bounds[3] + 4
        extra = [LineString([(w / 2 - w * 0.19, y), (w / 2 + w * 0.19, y)]).buffer(_line(0.5, dims) / 2)]
    corner = min(10.0, w / 4)
    outline = box(corner, corner, w - corner, h - corner).buffer(corner, 32)
    # الكفر جاهز من المورد: حفر فقط، وحدّه مرجع للمحاذاة.
    return Drawing(w, h, engrave=unary_union([text, *extra]), guide=[outline])


def _case_check(params: dict[str, Any]) -> dict[str, str]:
    if params.get(_STYLE) == _MONO_STYLE and len(str(params.get("النص", "")).replace(" ", "")) > 2:
        return {"النص": "two_letters"}
    return {}


GENERATORS: dict[str, Generator] = {
    "arched_card": Generator(_card_slots, _card_draw),
    "letter_keychain": Generator(_key_slots, _key_draw, _key_check),
    "jar_lid": Generator(_lid_slots, _lid_draw),
    "case_name": Generator(_case_slots, _case_draw, _case_check),
}


# ---------- كتابة SVG ----------


def _ring_d(coords) -> str:
    pts = list(coords)
    return "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in pts[:-1]) + " Z"


def path_d(shape: BaseGeometry) -> str:
    polys = shape.geoms if isinstance(shape, MultiPolygon) else [shape]
    out: list[str] = []
    for poly in polys:
        if poly.is_empty or not isinstance(poly, Polygon):
            continue
        out.append(_ring_d(poly.exterior.coords))
        out.extend(_ring_d(ring.coords) for ring in poly.interiors)
    return " ".join(out)


def to_svg(drawing: Drawing) -> str:
    """لا نص للعميل في الملف: مسارات وأرقام فقط، فلا حقن ولا خط مطلوب على جهاز الآلة."""
    layers = [
        ("engrave", ENGRAVE, path_d(drawing.engrave)),
        ("cut", CUT, " ".join(path_d(shape) for shape in drawing.cut)),
        ("guide", GUIDE, " ".join(path_d(shape) for shape in drawing.guide)),
    ]
    body = "\n".join(
        f'  <g id="{label}"><path {style} fill-rule="evenodd" d="{d}"/></g>'
        for label, style, d in layers
        if d
    )
    w, h = drawing.width, drawing.height
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" '
        f'viewBox="0 0 {w:.2f} {h:.2f}">\n{body}\n</svg>\n'
    )
