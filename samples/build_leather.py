"""يولّد ملفات SVG لعيّنات حفر الجلد النباتي الدباغة على xTool P2S.

حفر فقط، لا قص: الكفر جاهز من المورد، والقصاصة تُوضع كما هي. الأزرق
المتقطع مرجع يُطفأ إخراجه. يعيد استعمال تحويل النص من build_samples.

مقاسات الكفرات تقريبية: أبعاد الهاتف المنشورة مع نحو 1.5 مم لكل جانب،
ومنطقة الكاميرا محجوزة بهامش. تُطابق على الكفر الحقيقي بكاميرا الآلة.

التشغيل: python laser-cases/samples/build_leather.py
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from build_samples import (
    ENGRAVE,
    GUIDE,
    NAME_B,
    ArabicText,
    fit,
    path_d,
    write_svg,
)

# اسم للعيّنة فقط، لا لشخص بعينه.
NAME = NAME_B
INITIALS = "ن ع"


@dataclass(frozen=True)
class Phone:
    slug: str
    label: str
    w: float  # عرض الكفر (مم)
    h: float  # طول الكفر (مم)
    radius: float
    camera: tuple[float, float, float, float]  # المنطقة المحجوزة: x, y, عرض, طول


PHONES = (
    # آيفون 17: 149.6 × 71.5 مم. الكاميرا عمود في الأعلى يسارًا من الخلف.
    Phone("ايفون17", "آيفون 17", 74.5, 152.5, 11.0, (4.0, 4.0, 36.0, 48.0)),
    # جالكسي S25: 146.9 × 70.5 مم. ثلاث عدسات عمودية في الأعلى يسارًا.
    Phone("جالكسي_S25", "جالكسي S25", 73.5, 150.0, 9.0, (4.0, 4.0, 26.0, 56.0)),
)


def _rounded(w: float, h: float, r: float, x: float = 0.0, y: float = 0.0):
    return box(x + r, y + r, x + w - r, y + h - r).buffer(r, 64)


def _ring(shape, width: float):
    return shape.difference(shape.buffer(-width))


def case_name(phone: Phone, thuluth: ArabicText, m: float = 4.0):
    """الاسم أفقيًا بخط الثلث، وتحته خط رفيع، في الثلث الأسفل من الظهر."""
    cx = m + phone.w / 2
    cy = m + phone.h * 0.64
    name = fit(thuluth.shape(NAME, 20), cx, cy, 46, 20)
    _, _, _, maxy = name.bounds
    rule = LineString([(cx - 14, maxy + 4), (cx + 14, maxy + 4)]).buffer(0.25)
    return _case_svg(phone, m, "اسم", "الاسم بخط الثلث", unary_union([name, rule]))


def case_monogram(phone: Phone, thuluth: ArabicText, m: float = 4.0):
    """حرفان داخل دائرتين، في منتصف الظهر تحت الكاميرا."""
    cx = m + phone.w / 2
    cy = m + phone.h * 0.6
    outer = _ring(Point(cx, cy).buffer(17, 256), 0.8)
    inner = _ring(Point(cx, cy).buffer(15, 256), 0.3)
    letters = fit(thuluth.shape(INITIALS, 20), cx, cy, 20, 15)
    return _case_svg(
        phone, m, "حرفان", "حرفان في دائرة", unary_union([outer, inner, letters])
    )


def _case_svg(phone: Phone, m: float, slug: str, title: str, engrave):
    outline = _rounded(phone.w, phone.h, phone.radius, m, m)
    cx, cy, cw, ch = phone.camera
    camera = _rounded(cw, ch, 6.0, m + cx, m + cy)
    if engrave.intersects(camera.buffer(3)):
        raise ValueError(f"الحفر يقترب من الكاميرا في {phone.label}")
    if not outline.buffer(-6).contains(engrave):
        raise ValueError(f"الحفر قريب من حافة الكفر في {phone.label}")
    return write_svg(
        f"كفر_{phone.slug}_{slug}.svg",
        phone.w + 2 * m,
        phone.h + 2 * m,
        f"{title} على ظهر كفر {phone.label} (الكفر من الخلف)",
        [
            ("engrave", ENGRAVE, path_d(engrave)),
            ("guide", GUIDE, path_d(outline) + " " + path_d(camera)),
        ],
    )


def _ar(n: int) -> str:
    """أرقام عربية مشرقية، فلا يقلبها ترتيب الاتجاه."""
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def legibility_sheet(thuluth: ArabicText, naskh: ArabicText):
    """قصاصة 90 × 80 مم: أصغر خط يُقرأ وأرفع خط يبقى بعد الحفر."""
    m = 4.0
    w, h = 90.0, 80.0
    parts = []
    y = m + 4
    # الاسم بخط الثلث بأطوال 4 إلى 14 مم، والطول مكتوب يمينه.
    for size in (14, 10, 8, 6, 4):
        word = fit(thuluth.shape(NAME, 20), m + 34, y + size / 2, 60, size)
        label = fit(naskh.shape(f"{_ar(size)} مم", 10), m + w - 10, y + size / 2, 14, 3)
        parts += [word, label]
        y += size + 3.5
    # النسخ للنص الصغير: 3 و2 مم.
    for size in (3, 2):
        word = fit(naskh.shape("الخط العربي", 10), m + 34, y + size / 2, 60, size)
        label = fit(
            naskh.shape(f"نسخ {_ar(size)}", 10), m + w - 10, y + size / 2, 14, 2.5
        )
        parts += [word, label]
        y += size + 3.0
    # خطوط بعرض 0.2 و0.4 و0.8 مم.
    for i, width in enumerate((0.2, 0.4, 0.8)):
        x = m + 8 + i * 12
        parts.append(LineString([(x, y + 2), (x + 8, y + 2)]).buffer(width / 2))
    engrave = unary_union(parts)
    if engrave.bounds[3] > m + h - 1:
        raise ValueError("الاختبار أطول من القصاصة")
    return write_svg(
        "جلد_اختبار_الخط.svg",
        w + 2 * m,
        h + 2 * m,
        "قصاصة جلد 90 × 80 مم: أحجام الخط وعرض الخطوط",
        [
            ("engrave", ENGRAVE, path_d(engrave)),
            ("guide", GUIDE, path_d(box(m, m, m + w, m + h))),
        ],
    )


def main():
    thuluth = ArabicText("DTHULUTH.TTF")
    naskh = ArabicText("DTNASKH0.TTF")
    made = [legibility_sheet(thuluth, naskh)]
    for phone in PHONES:
        made += [case_name(phone, thuluth), case_monogram(phone, thuluth)]
    for name in made:
        print(name)


if __name__ == "__main__":
    main()
