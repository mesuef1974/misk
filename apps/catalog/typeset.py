"""تحويل النص إلى مسارات: تشكيل HarfBuzz (وصل وتشكيل ومزج لغتين) ثم حدود الحروف أشكالًا هندسية.

الناتج بوحدة الإم (إم = 1)، y للأسفل وخط القاعدة عند y=0، فيُحجَّم بمقاس الخط بالمليمتر مباشرة.
الخطوط من `brand/misk/fonts` برخصة OFL؛ لا خط نظام، فالخادم والمعاينة وملف القص من الملف نفسه.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import uharfbuzz as hb
from bidi import get_display
from django.conf import settings
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

FONTS_DIR = Path(settings.BASE_DIR) / "brand" / "misk" / "fonts"
CURVE_STEPS = 8
# نص مرجعي لمتوسط عرض الحرف: أسماء شائعة بالحرفين، بلا مسافات.
_REFERENCE = {"ar": "عبدالرحمنمحمدنورةفاطمةسلطانمريمخالد", "en": "AbdulrahmanMohammedNooraFatima"}


class TypesetError(ValueError):
    """حرف لا يحمله الخط، أو نص لا يُخرج شكلًا."""


@dataclass(frozen=True)
class FontSpec:
    file: str
    variations: tuple[tuple[str, float], ...] = ()


FONTS: dict[str, FontSpec] = {
    "cairo": FontSpec("Cairo[slnt,wght].ttf", (("wght", 600.0),)),
    "almarai": FontSpec("Almarai-Regular.ttf"),
}
DEFAULT_FONT = "cairo"


class _FlatPen:
    """يسطّح منحنيات الحرف إلى مضلعات (واجهة قلم fontTools التي يستدعيها HarfBuzz)."""

    def __init__(self) -> None:
        self.contours: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []

    def moveTo(self, p):  # noqa: N802
        self._cur = [p]

    def lineTo(self, p):  # noqa: N802
        self._cur.append(p)

    def curveTo(self, p1, p2, p3):  # noqa: N802
        p0 = self._cur[-1]
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            u = 1 - t
            a, b, c, d = u**3, 3 * u * u * t, 3 * u * t * t, t**3
            self._cur.append(
                (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])
            )

    def qCurveTo(self, *points):  # noqa: N802
        # نقاط تحكم متتالية بلا نقطة على المنحنى بينها: النقطة الضمنية منتصفهما (TrueType).
        controls, end = list(points[:-1]), points[-1]
        for index, control in enumerate(controls):
            nxt = controls[index + 1] if index + 1 < len(controls) else None
            target = end if nxt is None else ((control[0] + nxt[0]) / 2, (control[1] + nxt[1]) / 2)
            p0 = self._cur[-1]
            for i in range(1, CURVE_STEPS + 1):
                t = i / CURVE_STEPS
                u = 1 - t
                self._cur.append(
                    (
                        u * u * p0[0] + 2 * u * t * control[0] + t * t * target[0],
                        u * u * p0[1] + 2 * u * t * control[1] + t * t * target[1],
                    )
                )
        if not controls:
            self._cur.append(end)

    def closePath(self):  # noqa: N802
        if len(self._cur) >= 3:
            self.contours.append(self._cur)
        self._cur = []

    endPath = closePath  # noqa: N815


def _signed_area(ring: list[tuple[float, float]]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1], strict=True)) / 2


def _contours_to_shape(contours: list[list[tuple[float, float]]]) -> BaseGeometry:
    """قاعدة اللف غير الصفري: اتجاه أكبر كفاف هو الخارج، وعكسه ثقوب. تراكب كفافَين (خط متغيّر) لا يصير ثقبًا."""
    if not contours:
        return Polygon()
    areas = [_signed_area(ring) for ring in contours]
    outer_sign = 1 if max(areas, key=abs) > 0 else -1
    outers: list[BaseGeometry] = []
    holes: list[BaseGeometry] = []
    for ring, area in zip(contours, areas, strict=True):
        poly = Polygon(ring).buffer(0)
        if poly.is_empty:
            continue
        (outers if area * outer_sign > 0 else holes).append(poly)
    shape = unary_union(outers)
    return shape.difference(unary_union(holes)) if holes else shape


class _Face:
    def __init__(self, spec: FontSpec) -> None:
        path = FONTS_DIR / spec.file
        try:
            blob = hb.Blob.from_file_path(str(path))
        except Exception as exc:  # uharfbuzz يرمي أنواعًا مختلفة بحسب الإصدار
            raise TypesetError(f"ملف الخط غير موجود: {spec.file}") from exc
        self.face = hb.Face(blob)
        self.font = hb.Font(self.face)
        if spec.variations:
            self.font.set_variations(dict(spec.variations))
        self.upem = self.face.upem
        self._glyphs: dict[int, BaseGeometry] = {}

    def glyph(self, gid: int) -> BaseGeometry:
        if gid not in self._glyphs:
            pen = _FlatPen()
            self.font.draw_glyph_with_pen(gid, pen)
            self._glyphs[gid] = _contours_to_shape(pen.contours)
        return self._glyphs[gid]


@cache
def _face(font_key: str) -> _Face:
    try:
        return _Face(FONTS[font_key])
    except KeyError as exc:
        raise TypesetError(f"خط غير معروف: {font_key}") from exc


def _is_rtl(ch: str) -> bool:
    return unicodedata.bidirectional(ch) in {"R", "AL", "NSM"}


def _visual_runs(text: str) -> list[tuple[str, str]]:
    """مقاطع النص بترتيب العرض من اليسار: (النص بترتيبه المنطقي، الاتجاه).

    خوارزمية bidi ترتّب السطر كله؛ ثم يُقسم المعروض إلى مقاطع متصلة الاتجاه، ومقطع العربية يُعكس ليعود
    منطقيًّا فيشكّله HarfBuzz (الوصل يحتاج الترتيب المنطقي).
    """
    visual = get_display(text)
    runs: list[tuple[str, str]] = []
    current, rtl = "", False
    for ch in visual:
        ch_rtl = _is_rtl(ch)
        if current and ch_rtl != rtl:
            runs.append((current[::-1] if rtl else current, "rtl" if rtl else "ltr"))
            current = ""
        current, rtl = current + ch, ch_rtl
    if current:
        runs.append((current[::-1] if rtl else current, "rtl" if rtl else "ltr"))
    return runs


def _shape_run(face: _Face, text: str, direction: str) -> tuple[list[BaseGeometry], float]:
    buf = hb.Buffer()
    buf.add_str(text)
    buf.direction = direction
    buf.guess_segment_properties()
    hb.shape(face.font, buf, {})
    parts: list[BaseGeometry] = []
    x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        if info.codepoint == 0:
            ch = text[info.cluster] if info.cluster < len(text) else "?"
            raise TypesetError(f"الحرف «{ch}» (U+{ord(ch):04X}) غير موجود في الخط")
        glyph = face.glyph(info.codepoint)
        if not glyph.is_empty:
            parts.append(affinity.translate(glyph, xoff=x + pos.x_offset, yoff=pos.y_offset))
        x += pos.x_advance
    return parts, x


def measure(text: str, font_key: str = DEFAULT_FONT) -> float:
    """عرض السطر بالإم (مجموع التقدّمات)."""
    face = _face(font_key)
    return sum(_shape_run(face, run, direction)[1] for run, direction in _visual_runs(text)) / face.upem


def outline(text: str, font_key: str = DEFAULT_FONT) -> BaseGeometry:
    """شكل السطر بالإم، يبدأ من x=0 وخط القاعدة عند y=0 (y للأسفل كما في SVG)."""
    face = _face(font_key)
    parts: list[BaseGeometry] = []
    x = 0.0
    for run, direction in _visual_runs(unicodedata.normalize("NFC", text)):
        glyphs, advance = _shape_run(face, run, direction)
        parts.extend(affinity.translate(g, xoff=x) for g in glyphs)
        x += advance
    shape = unary_union(parts) if parts else Polygon()
    if shape.is_empty:
        raise TypesetError("النص لا يُخرج شكلًا يُحفر")
    scale = 1 / face.upem
    return affinity.scale(shape, xfact=scale, yfact=-scale, origin=(0, 0))


@cache
def stroke_em(font_key: str) -> float:
    """سُمك جرّة القلم بالإم: عرض الألف المفردة، وهي جرّة رأسية واحدة في الخطين."""
    minx, _, maxx, _ = outline("ا", font_key).bounds
    return maxx - minx


@cache
def mean_advance_em(font_key: str) -> float:
    """متوسط عرض الحرف بالإم، الأوسع من العربية واللاتينية (فالحدّ المحسوب منه متحفّظ)."""
    return max(measure(sample, font_key) / len(sample) for sample in _REFERENCE.values())


def fit(shape: BaseGeometry, cx: float, cy: float, max_w: float, max_h: float) -> tuple[BaseGeometry, float]:
    """يحجّم الشكل ليدخل الصندوق ويوسّطه حول (cx, cy). يعيد الشكل ومقاس الإم الناتج بالمليمتر."""
    minx, miny, maxx, maxy = shape.bounds
    k = min(max_w / (maxx - minx), max_h / (maxy - miny))
    scaled = affinity.scale(shape, xfact=k, yfact=k, origin=(0, 0))
    minx, miny, maxx, maxy = scaled.bounds
    return affinity.translate(scaled, cx - (minx + maxx) / 2, cy - (miny + maxy) / 2), k
