"""قراءة ملف قص SVG بالمكتبة القياسية: المقاس الحقيقي، والعمليات بألوانها، وأطوالها، والمربع المرجعي.

نقي بلا Django ولا قاعدة: يأخذ بايتات ومفتاح ألوان ويعيد `Analysis`.

المقاس من `width/height` المصرَّحين، و`viewBox` يعطي نسبة الوحدة إلى المليمتر. ملفات Illustrator تُصدَّر بـ 72 نقطة
في البوصة، فقراءة وحداتها بـ 96 (افتراض أغلب البرامج) تصغّر التصميم بنسبة 72/96.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET  # noqa: S405 — يُقرأ بلا كيانات خارجية؛ expat يحدّ توسّع الكيانات.
from dataclasses import dataclass, field

SVG_NS = "{http://www.w3.org/2000/svg}"
MM_PER_UNIT = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "pt": 25.4 / 72,
    "pc": 25.4 / 6,
    "px": 25.4 / 96,
    "": 25.4 / 96,
}
REFERENCE_MM = 25.4
REFERENCE_TOLERANCE_MM = 1.0
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
CURVE_STEP = 0.5  # وحدات SVG لكل قطعة عند تقريب المنحنى؛ نصف دائرة بنصف قطر 5 يخطئ طولها بأقل من 0.05%.

Point = tuple[float, float]
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class SvgError(ValueError):
    pass


@dataclass
class Element:
    tag: str
    stroke: str
    fill: str
    polylines: list[list[Point]]  # بالمليمتر بعد التحويل
    node: ET.Element = field(repr=False)
    rule: tuple[str, str] | None = None  # (العملية، المادة) من مفتاح الألوان
    is_reference: bool = False

    @property
    def length_mm(self) -> float:
        return sum(math.dist(a, b) for line in self.polylines for a, b in zip(line, line[1:], strict=False))

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [x for line in self.polylines for x, _ in line]
        ys = [y for line in self.polylines for _, y in line]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)

    @property
    def bbox_area_mm2(self) -> float:
        x0, y0, x1, y1 = self.bbox
        return (x1 - x0) * (y1 - y0)


@dataclass
class Analysis:
    width_mm: float
    height_mm: float
    mm_per_unit: float
    operations: dict[str, dict]
    unknown_colors: dict[str, int]
    reference_mm: tuple[float, float] | None
    elements: list[Element] = field(repr=False, default_factory=list)

    def as_json(self) -> dict:
        return {
            "width_mm": round(self.width_mm, 1),
            "height_mm": round(self.height_mm, 1),
            "mm_per_unit": round(self.mm_per_unit, 6),
            "operations": self.operations,
            "unknown_colors": self.unknown_colors,
            "reference_mm": [round(v, 2) for v in self.reference_mm] if self.reference_mm else None,
        }


# ——— الألوان والأنماط ———

_NAMED = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "blue": "#0000ff", "green": "#008000"}


def normalize_color(value: str | None) -> str:
    value = (value or "").strip().lower()
    if value in ("", "none", "transparent"):
        return ""
    value = _NAMED.get(value, value)
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        return "#" + "".join(c * 2 for c in value[1:])
    if m := re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value):
        return "#" + "".join(f"{min(int(c), 255):02x}" for c in m.groups())
    return value


def _style(node: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    style = dict(inherited)
    for key in ("stroke", "fill"):
        if key in node.attrib:
            style[key] = node.attrib[key]
    for part in node.attrib.get("style", "").split(";"):
        if ":" in part:
            key, value = (s.strip() for s in part.split(":", 1))
            if key in ("stroke", "fill"):
                style[key] = value
    return style


# ——— الوحدات والتحويلات ———


def _length_mm(value: str) -> float | None:
    m = re.fullmatch(r"\s*([0-9.]+(?:e[-+]?\d+)?)\s*(mm|cm|in|pt|pc|px)?\s*", value or "", re.IGNORECASE)
    return float(m.group(1)) * MM_PER_UNIT[(m.group(2) or "").lower()] if m else None


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    return (
        a[0] * b[0] + a[2] * b[1],
        a[1] * b[0] + a[3] * b[1],
        a[0] * b[2] + a[2] * b[3],
        a[1] * b[2] + a[3] * b[3],
        a[0] * b[4] + a[2] * b[5] + a[4],
        a[1] * b[4] + a[3] * b[5] + a[5],
    )


def parse_transform(value: str) -> Matrix:
    matrix = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", value or ""):
        n = [float(v) for v in _NUMBER.findall(args)]
        if name == "matrix" and len(n) == 6:
            step = tuple(n)
        elif name == "translate" and n:
            step = (1, 0, 0, 1, n[0], n[1] if len(n) > 1 else 0)
        elif name == "scale" and n:
            step = (n[0], 0, 0, n[1] if len(n) > 1 else n[0], 0, 0)
        elif name == "rotate" and n:
            a = math.radians(n[0])
            cx, cy = (n[1], n[2]) if len(n) == 3 else (0, 0)
            rot = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            step = _multiply(_multiply((1, 0, 0, 1, cx, cy), rot), (1, 0, 0, 1, -cx, -cy))
        elif name == "skewX" and n:
            step = (1, 0, math.tan(math.radians(n[0])), 1, 0, 0)
        elif name == "skewY" and n:
            step = (1, math.tan(math.radians(n[0])), 0, 1, 0, 0)
        else:
            raise SvgError(f"تحويل غير مدعوم: {name}({args})")
        matrix = _multiply(matrix, step)  # type: ignore[arg-type]
    return matrix


def _apply(m: Matrix, p: Point) -> Point:
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


# ——— المسارات ———

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _segments(n: float) -> int:
    return max(16, min(4096, math.ceil(n / CURVE_STEP)))


def _bezier(points: list[Point]) -> list[Point]:
    """يقرّب منحنى بيزييه (تربيعي أو تكعيبي) بقطع على قدر طول مضلع التحكم."""
    count = _segments(sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False)))
    out = []
    for i in range(1, count + 1):
        t = i / count
        pts = points
        while len(pts) > 1:  # de Casteljau
            pts = [
                ((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1])
                for a, b in zip(pts, pts[1:], strict=False)
            ]
        out.append(pts[0])
    return out


def _arc(p0: Point, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, p1: Point) -> list[Point]:
    """قوس SVG بصيغة النقطتين إلى الصيغة المركزية (SVG 1.1، الملحق F.6.5) ثم نقاط عليه."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p, y1p = cos_p * dx + sin_p * dy, -sin_p * dx + cos_p * dy
    scale = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    start = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    count = _segments(abs(delta) * max(rx, ry))
    out = []
    for i in range(1, count + 1):
        t = start + delta * i / count
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cos_p * x - sin_p * y + cx, sin_p * x + cos_p * y + cy))
    out[-1] = p1
    return out


def path_polylines(d: str) -> list[list[Point]]:
    """يحوّل `d` إلى خطوط متعددة بوحدات الملف، خطًّا لكل مسار فرعي."""
    tokens = _TOKEN.findall(d or "")
    lines: list[list[Point]] = []
    current: list[Point] = []
    pos: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    last_ctrl: Point | None = None
    last_cmd = ""
    i, cmd = 0, ""
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        elif not cmd:
            raise SvgError("مسار يبدأ برقم لا بأمر")
        upper, rel = cmd.upper(), cmd.islower()
        arity = _ARITY[upper]
        if upper == "Z":
            if current:
                current.append(start)
            pos, last_ctrl, last_cmd = start, None, "Z"
            current = []
            continue
        if i + arity > len(tokens) or any(t.isalpha() for t in tokens[i : i + arity]):
            raise SvgError(f"أرقام ناقصة بعد الأمر {cmd}")
        n = [float(t) for t in tokens[i : i + arity]]
        i += arity
        ox, oy = pos if rel else (0.0, 0.0)
        if upper == "M":
            pos = (ox + n[0], oy + n[1])
            start = pos
            current = [pos]
            lines.append(current)
            cmd = "l" if rel else "L"  # أزواج تالية لـ M خطوط
            last_ctrl, last_cmd = None, "M"
            continue
        if not current:
            current = [pos]
            lines.append(current)
        if upper in ("L", "H", "V"):
            if upper == "L":
                new = (ox + n[0], oy + n[1])
            elif upper == "H":
                new = (ox + n[0], pos[1])
            else:
                new = (pos[0], oy + n[0])
            current.append(new)
            ctrl = None
        elif upper in ("C", "S"):
            if upper == "C":
                c1 = (ox + n[0], oy + n[1])
                rest = n[2:]
            else:
                c1 = (
                    (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1])
                    if last_cmd in "CS" and last_ctrl
                    else pos
                )
                rest = n
            c2 = (ox + rest[0], oy + rest[1])
            new = (ox + rest[2], oy + rest[3])
            current.extend(_bezier([pos, c1, c2, new]))
            ctrl = c2
        elif upper in ("Q", "T"):
            if upper == "Q":
                c = (ox + n[0], oy + n[1])
                new = (ox + n[2], oy + n[3])
            else:
                c = (
                    (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1])
                    if last_cmd in "QT" and last_ctrl
                    else pos
                )
                new = (ox + n[0], oy + n[1])
            current.extend(_bezier([pos, c, new]))
            ctrl = c
        else:  # A
            new = (ox + n[5], oy + n[6])
            current.extend(_arc(pos, n[0], n[1], n[2], bool(n[3]), bool(n[4]), new))
            ctrl = None
        pos, last_ctrl, last_cmd = new, ctrl, upper
    return [line for line in lines if len(line) > 1]


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> list[Point]:
    count = _segments(2 * math.pi * max(rx, ry))
    return [
        (cx + rx * math.cos(2 * math.pi * i / count), cy + ry * math.sin(2 * math.pi * i / count))
        for i in range(count + 1)
    ]


def shape_polylines(node: ET.Element) -> list[list[Point]]:
    tag = node.tag.removeprefix(SVG_NS)
    a = node.attrib

    def num(key: str, default: float = 0.0) -> float:
        return float(a.get(key, default) or default)

    if tag == "path":
        return path_polylines(a.get("d", ""))
    if tag == "rect":
        x, y, w, h = num("x"), num("y"), num("width"), num("height")
        rx = num("rx", num("ry"))
        ry = num("ry", rx)
        if rx or ry:
            rx, ry = min(rx, w / 2), min(ry, h / 2)
            d = (
                f"M{x + rx},{y}H{x + w - rx}A{rx},{ry} 0 0 1 {x + w},{y + ry}V{y + h - ry}"
                f"A{rx},{ry} 0 0 1 {x + w - rx},{y + h}H{x + rx}A{rx},{ry} 0 0 1 {x},{y + h - ry}"
                f"V{y + ry}A{rx},{ry} 0 0 1 {x + rx},{y}Z"
            )
            return path_polylines(d)
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
    if tag == "circle":
        return [_ellipse(num("cx"), num("cy"), num("r"), num("r"))]
    if tag == "ellipse":
        return [_ellipse(num("cx"), num("cy"), num("rx"), num("ry"))]
    if tag == "line":
        return [[(num("x1"), num("y1")), (num("x2"), num("y2"))]]
    values = [float(v) for v in _NUMBER.findall(a.get("points", ""))]
    pts = list(zip(values[::2], values[1::2], strict=False))
    if tag == "polygon" and pts:
        pts.append(pts[0])
    return [pts] if len(pts) > 1 else []


# ——— القراءة الكاملة ———


def parse_root(data: bytes) -> ET.Element:
    if b"<!ENTITY" in data or b"<!DOCTYPE" in data:
        raise SvgError("ملف SVG فيه DOCTYPE أو كيانات؛ لا يُقرأ")
    try:
        root = ET.fromstring(data)  # noqa: S314 — DOCTYPE مرفوض أعلاه
    except ET.ParseError as exc:
        raise SvgError(f"ملف SVG غير صالح: {exc}") from exc
    if root.tag != f"{SVG_NS}svg":
        raise SvgError("الجذر ليس svg")
    return root


def _units(root: ET.Element) -> tuple[float, float, float, Matrix]:
    """(العرض مم، الارتفاع مم، مم لكل وحدة، مصفوفة viewBox)."""
    view = [float(v) for v in _NUMBER.findall(root.attrib.get("viewBox", ""))]
    width, height = _length_mm(root.attrib.get("width", "")), _length_mm(root.attrib.get("height", ""))
    if len(view) == 4 and view[2] > 0 and view[3] > 0:
        sx = width / view[2] if width else MM_PER_UNIT[""]
        sy = height / view[3] if height else sx
        width, height = view[2] * sx, view[3] * sy
        return width, height, sx, (sx, 0.0, 0.0, sy, -view[0] * sx, -view[1] * sy)
    if width is None or height is None:
        raise SvgError("لا viewBox ولا width/height: المقاس مجهول")
    s = MM_PER_UNIT[""]
    return width, height, s, (s, 0.0, 0.0, s, 0.0, 0.0)


def _walk(node: ET.Element, matrix: Matrix, style: dict[str, str], out: list[Element]) -> None:
    for child in node:
        tag = child.tag.removeprefix(SVG_NS) if isinstance(child.tag, str) else ""
        if tag in ("defs", "clipPath", "mask", "symbol", "metadata", "title", "desc", "style"):
            continue
        m = _multiply(matrix, parse_transform(child.attrib.get("transform", "")))
        s = _style(child, style)
        if tag == "g" or tag == "a":
            _walk(child, m, s, out)
        elif tag in SHAPES:
            lines = [[_apply(m, p) for p in line] for line in shape_polylines(child)]
            if lines:
                out.append(
                    Element(
                        tag,
                        normalize_color(s.get("stroke")),
                        normalize_color(s.get("fill", "#000")),
                        lines,
                        child,
                    )
                )


def _is_reference(el: Element, key: dict[str, dict]) -> bool:
    """مربع المقاس المرجعي: معبّأ بلون خارج المفتاح، وإحاطته 25.4 مم تقريبًا في البعدين."""
    if not el.fill or el.fill in key:
        return False
    x0, y0, x1, y1 = el.bbox
    return all(abs(v - REFERENCE_MM) <= REFERENCE_TOLERANCE_MM for v in (x1 - x0, y1 - y0))


def analyze(data: bytes, color_key: dict[str, dict]) -> Analysis:
    """`color_key`: لون → {"operation": cut|score|engrave, "material": نوع المادة}."""
    return _analyze_root(parse_root(data), color_key)


def _analyze_root(root: ET.Element, color_key: dict[str, dict]) -> Analysis:
    key = {normalize_color(c): v for c, v in color_key.items()}
    width, height, mm_per_unit, base = _units(root)
    elements: list[Element] = []
    _walk(root, base, {}, elements)

    reference = next((el for el in elements if _is_reference(el, key)), None)
    if reference:
        reference.is_reference = True
    operations: dict[str, dict] = {}
    unknown: dict[str, int] = {}
    for el in elements:
        if el is reference:
            continue
        color = el.stroke or el.fill
        rule = key.get(color)
        if not rule:
            unknown[color or "none"] = unknown.get(color or "none", 0) + 1
            continue
        el.rule = (rule["operation"], rule.get("material", ""))
        group = operations.setdefault(
            f"{rule['operation']}:{rule.get('material', '')}",
            {
                "operation": rule["operation"],
                "material": rule.get("material", ""),
                "count": 0,
                "length_mm": 0.0,
                "bbox_area_mm2": 0.0,
            },
        )
        group["count"] += 1
        group["length_mm"] += el.length_mm
        group["bbox_area_mm2"] += el.bbox_area_mm2
    for group in operations.values():
        group["length_mm"] = round(group["length_mm"], 1)
        group["bbox_area_mm2"] = round(group["bbox_area_mm2"], 1)
    ref = None
    if reference:
        x0, y0, x1, y1 = reference.bbox
        ref = (x1 - x0, y1 - y0)
    return Analysis(width, height, mm_per_unit, operations, unknown, ref, elements)


def outer_area_mm2(analysis: Analysis, material: str) -> float:
    """مساحة إحاطة القطع الخارجية بمادة: عناصر القص التي لا تقع إحاطتها داخل قطعة أخرى."""
    cuts = [el.bbox for el in analysis.elements if el.rule == ("cut", material)]

    def inside(a: tuple, b: tuple) -> bool:
        return a != b and b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2] and a[3] <= b[3]

    outer = [a for a in cuts if not any(inside(a, b) for b in cuts)]
    return sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in outer)


def ready_to_cut(data: bytes, color_key: dict[str, dict]) -> bytes:
    """الأصل بلا المربع المرجعي، وبعرض وارتفاع بالمليمتر: يقرؤه كل برنامج قص بالمقاس نفسه."""
    root = parse_root(data)
    analysis = _analyze_root(root, color_key)
    parents = {child: parent for parent in root.iter() for child in parent}
    for el in analysis.elements:
        if el.is_reference:
            parents[el.node].remove(el.node)
    ET.register_namespace("", SVG_NS[1:-1])
    root.set("width", f"{analysis.width_mm:.3f}mm")
    root.set("height", f"{analysis.height_mm:.3f}mm")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
