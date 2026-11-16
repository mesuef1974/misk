"""يولّد ملفات SVG لعيّنات توزيعات المناسبات على xTool P2S.

الوحدة مليمتر. طبقات xTool Creative Space تُميَّز باللون:
- أحمر #ff0000 خط رفيع: قص.
- أسود #000000 تعبئة: حفر.
- أزرق #0000ff خط: مرجع لا يُخرج (يُطفأ في البرنامج).

النص يتحول إلى مسارات، فلا يحتاج الملف خطًّا على جهاز الآلة. الخطوط
تُقرأ من C:\\Windows\\Fonts ولا تُنسخ إلى المستودع (رخصتها لا تسمح).

التشغيل: python laser-cases/samples/build_samples.py
"""

from __future__ import annotations

import math
from pathlib import Path

from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

FONTS_DIR = Path(r"C:\Windows\Fonts")
OUT = Path(__file__).resolve().parent
CUT = 'fill="none" stroke="#ff0000" stroke-width="0.1"'
ENGRAVE = 'fill="#000000" stroke="none"'
GUIDE = 'fill="none" stroke="#0000ff" stroke-width="0.2" stroke-dasharray="1 1"'

# أسماء للعيّنة فقط، لا لأشخاص بأعينهم.
NAME_A = "عبدالله"

# خطوط DecoType لا تحمل رمز «الله» المركّب U+FDF2، فتُكتب حروفه منفصلة.
RESHAPER = ArabicReshaper(
    configuration={
        "ARABIC LIGATURE ALLAH": False,
        "ARABIC LIGATURE ALLAH WITHOUT LETTER HEH": False,
    }
)
NAME_B = "نورة"
DATE = "٢٠ . ٣ . ٢٠٢٧"


# ---------- تحويل النص إلى أشكال ----------


class _FlatPen(BasePen):
    """يسطّح منحنيات الحرف إلى مضلعات بدقة ثابتة."""

    def __init__(self, glyphset, steps: int = 12):
        super().__init__(glyphset)
        self.steps = steps
        self.contours: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []

    def _moveTo(self, p):
        self._cur = [p]

    def _lineTo(self, p):
        self._cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self._cur.append(
                (
                    u**3 * p0[0]
                    + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0]
                    + t**3 * p3[0],
                    u**3 * p0[1]
                    + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1]
                    + t**3 * p3[1],
                )
            )

    def _qCurveToOne(self, p1, p2):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self._cur.append(
                (
                    u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
                )
            )

    def _closePath(self):
        if len(self._cur) >= 3:
            self.contours.append(self._cur)
        self._cur = []

    _endPath = _closePath


def _contours_to_shape(contours):
    """زوجي-فردي: الثقوب الداخلية (مثل عين الواو) تبقى فارغة."""
    shape = Polygon()
    for c in contours:
        poly = Polygon(c).buffer(0)
        if not poly.is_empty:
            shape = shape.symmetric_difference(poly)
    return shape


class ArabicText:
    """تشكيل بسيط بصيغ العرض (Presentation Forms)، يكفي خطوط DecoType
    التي لا تعتمد على GPOS."""

    def __init__(self, font_file: str):
        self.font = TTFont(str(FONTS_DIR / font_file))
        self.cmap = self.font.getBestCmap()
        self.glyphs = self.font.getGlyphSet()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]

    def shape(self, text: str, height_mm: float):
        """يعيد شكل shapely للنص بارتفاع إم = height_mm، يبدأ من x=0
        وخط القاعدة عند y=0 (y للأسفل كما في SVG)."""
        visual = get_display(RESHAPER.reshape(text))
        scale = height_mm / self.upm
        x = 0.0
        parts = []
        for ch in visual:
            gname = self.cmap.get(ord(ch))
            if gname is None:
                raise ValueError(f"الحرف {ch!r} (U+{ord(ch):04X}) غير موجود في الخط")
            pen = _FlatPen(self.glyphs)
            self.glyphs[gname].draw(pen)
            g = _contours_to_shape(pen.contours)
            if not g.is_empty:
                g = affinity.translate(g, xoff=x)
                parts.append(g)
            x += self.hmtx[gname][0]
        shape = unary_union(parts) if parts else Polygon()
        # من وحدات الخط (y للأعلى) إلى مم (y للأسفل).
        return affinity.scale(shape, xfact=scale, yfact=-scale, origin=(0, 0))


def fit(shape, cx: float, cy: float, max_w: float, max_h: float):
    """يحجّم الشكل ليدخل في الصندوق ويوسّطه حول (cx, cy)."""
    minx, miny, maxx, maxy = shape.bounds
    k = min(max_w / (maxx - minx), max_h / (maxy - miny))
    s = affinity.scale(shape, xfact=k, yfact=k, origin=(0, 0))
    minx, miny, maxx, maxy = s.bounds
    return affinity.translate(s, cx - (minx + maxx) / 2, cy - (miny + maxy) / 2)


# ---------- كتابة SVG ----------


def _ring_d(coords) -> str:
    pts = list(coords)
    return "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in pts[:-1]) + " Z"


def path_d(shape) -> str:
    polys = shape.geoms if isinstance(shape, MultiPolygon) else [shape]
    out = []
    for p in polys:
        if p.is_empty:
            continue
        out.append(_ring_d(p.exterior.coords))
        out.extend(_ring_d(r.coords) for r in p.interiors)
    return " ".join(out)


def write_svg(
    name: str, w: float, h: float, title: str, layers: list[tuple[str, str, str]]
):
    body = []
    for label, style, d in layers:
        body.append(
            f'  <g id="{label}"><path {style} fill-rule="evenodd" d="{d}"/></g>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" '
        f'viewBox="0 0 {w:.2f} {h:.2f}">\n  <title>{title}</title>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )
    (OUT / name).write_text(svg, encoding="utf-8")
    return name


def outline_d(shape) -> str:
    """حدود الشكل خطًّا (للقص)."""
    return path_d(shape)


# ---------- العيّنات ----------


def arched_card(thuluth: ArabicText, naskh: ArabicText):
    """بطاقة مقوّسة 60 × 90 مم من خشب 3 مم، فيها ثقب للشريطة."""
    w, h, m = 60.0, 90.0, 4.0
    r = w / 2
    card = unary_union(
        [Point(m + r, m + r).buffer(r, 128), box(m, m + r, m + w, m + h)]
    )
    hole = Point(m + r, m + 8).buffer(2.0, 64)
    names = unary_union(
        [
            fit(thuluth.shape(NAME_A, 20), m + r, m + 36, 44, 16),
            fit(thuluth.shape("و", 20), m + r, m + 50, 10, 8),
            fit(thuluth.shape(NAME_B, 20), m + r, m + 62, 40, 15),
        ]
    )
    date = fit(naskh.shape(DATE, 10), m + r, m + 80, 34, 4.5)
    # إطار محفور داخل الحافة.
    inner = card.buffer(-3.0)
    frame = inner.difference(inner.buffer(-0.6))
    engrave = unary_union([names, date, frame])
    return write_svg(
        "بطاقة_مقوسة.svg",
        w + 2 * m,
        h + 2 * m,
        "بطاقة مقوّسة بالاسمين، 60 × 90 مم",
        [
            ("engrave", ENGRAVE, path_d(engrave)),
            ("cut", CUT, outline_d(card) + " " + outline_d(hole)),
        ],
    )


def _bridge(shape, width: float):
    """يصل أجزاء الحرف المنفصلة (النقاط) بأقرب جزء، فتخرج قطعة قص واحدة."""
    parts = sorted(getattr(shape, "geoms", [shape]), key=lambda g: -g.area)
    joined = parts[0]
    for part in parts[1:]:
        a, b = nearest_points(joined, part)
        joined = unary_union([joined, part, LineString([a, b]).buffer(width / 2, 16)])
    return joined


def letter_keychain(thuluth: ArabicText, letter: str = "ن"):
    """ميدالية حرف: الحرف نفسه مقصوص بحافة 2.5 مم وحلقة تعليق."""
    m = 4.0
    glyph = fit(thuluth.shape(letter, 40), 30, 34, 36, 40)
    body = _bridge(glyph.buffer(2.5, 32), width=5.0)
    # الحلقة فوق أعلى نقطة في الجسم، فتتصل به دائمًا.
    top = min(body.exterior.coords, key=lambda p: p[1])
    ring_c = Point(top[0], top[1] - 3.0)
    ring = ring_c.buffer(5.0, 64)
    shape = unary_union([body, ring])
    hole = ring_c.buffer(2.0, 64)
    dx, dy = m - shape.bounds[0], m - shape.bounds[1]
    shape, glyph, hole = (affinity.translate(g, dx, dy) for g in (shape, glyph, hole))
    _, _, maxx, maxy = shape.bounds
    return write_svg(
        "ميدالية_حرف.svg",
        maxx + m,
        maxy + m,
        f"ميدالية الحرف «{letter}»، أكريليك أو خشب 3 مم",
        [
            ("engrave", ENGRAVE, path_d(glyph)),
            ("cut", CUT, outline_d(shape) + " " + outline_d(hole)),
        ],
    )


def jar_lid(thuluth: ArabicText, naskh: ArabicText, diameter: float = 70.0):
    """غطاء برطمان خشبي جاهز: حفر فقط، والدائرة الزرقاء للمحاذاة."""
    m = 4.0
    r = diameter / 2
    c = Point(m + r, m + r)
    ring = c.buffer(r - 3, 256).difference(c.buffer(r - 3.8, 256))
    ring2 = c.buffer(r - 5, 256).difference(c.buffer(r - 5.4, 256))
    # 24 نقطة زخرفية بين الحلقتين.
    dots = unary_union(
        [
            Point(c.x + (r - 4.4) * math.cos(a), c.y + (r - 4.4) * math.sin(a)).buffer(
                0.35, 16
            )
            for a in (2 * math.pi * i / 24 for i in range(24))
        ]
    )
    names = fit(
        thuluth.shape(f"{NAME_A}  و  {NAME_B}", 20), c.x, c.y - 3, 2 * r - 20, 20
    )
    date = fit(naskh.shape(DATE, 10), c.x, c.y + 15, 30, 4.5)
    engrave = unary_union([ring, ring2, names, date, dots])
    return write_svg(
        "غطاء_برطمان.svg",
        diameter + 2 * m,
        diameter + 2 * m,
        f"غطاء برطمان بقطر {diameter:g} مم: حفر فقط",
        [
            ("engrave", ENGRAVE, path_d(engrave)),
            ("guide", GUIDE, outline_d(c.buffer(r, 256))),
        ],
    )


def main():
    thuluth = ArabicText("DTHULUTH.TTF")
    naskh = ArabicText("DTNASKH0.TTF")
    made = [
        arched_card(thuluth, naskh),
        letter_keychain(thuluth),
        jar_lid(thuluth, naskh),
    ]
    for name in made:
        print(OUT / name)


if __name__ == "__main__":
    main()
