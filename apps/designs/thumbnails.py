"""مصغّرات صور عرض التصاميم الجاهزة: التوليد والذاكرة المؤقتة والتسخين، مشتركة بين المسار العام والمهمة الخلفية.

الذاكرة المؤقتة (Redis) تبقى بين النشرات، فالتسخين يلزم عند نشر تصميم جديد وعند انقضاء `THUMB_TTL`
لا عند كل نشر للشيفرة. الدالة idempotent: إعادتها تكتب القيمة نفسها."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import PurePosixPath

from django.core.cache import cache

from .models import DesignImage
from .validators import IMAGE_TYPES

THUMB_WIDTHS = (480, 960)  # البطاقة والمعرض؛ نسخة الواجهة في DesignCard.vue وDesignPage.vue
THUMB_TTL = 7 * 24 * 3600
# فك صورة PNG يحجز ~4 بايت للبكسل (RGBA)، و135 ميغابكسل ≈ 540 ميغابايت: في عملية الويب يُرفض ما فوق هذا الحد
# فيُخدَم الأصل مؤقتًا ويُصغَّر في العامل. JPEG يُخفَّض عند الفك داخل `thumbnail` (draft) فلا يحجز المقاس الكامل.
ON_DEMAND_MAX_PIXELS = 24_000_000


class TooHeavy(Exception):  # noqa: N818 — إشارة تحكّم لا خطأ
    """الصورة أثقل من أن تُصغَّر أثناء الطلب؛ يُؤجَّل التصغير إلى مهمة خلفية."""


def digest(image: DesignImage, width: int) -> str:
    """بصمة الصورة والعرض: من اسم الملف، فاستبدال الملف يبطل الذاكرة والـETag معًا."""
    return hashlib.sha256(f"{image.pk}:{image.file.name}:{width}".encode()).hexdigest()


def etag(image: DesignImage, width: int) -> str:
    return f'"{digest(image, width)[:20]}"'


def _cache_key(image: DesignImage, width: int) -> str:
    return f"design-image:{digest(image, width)}"


def cached(image: DesignImage, width: int) -> tuple[str, bytes] | None:
    return cache.get(_cache_key(image, width))


def _resize(data: bytes, width: int, *, on_demand: bool) -> bytes | None:
    """نسخة WebP بعرض `width` على الأكثر، أو None إن لم تلزم (الأصل أصغر) أو تعذّرت القراءة.

    يرفع `TooHeavy` أثناء الطلب لما فوق `ON_DEMAND_MAX_PIXELS`؛ والقياس من الترويسة قبل فك البكسلات."""
    try:
        from PIL import Image  # noqa: PLC0415 — اعتمادية اختيارية: بدونها يُخدَم الأصل

        with Image.open(BytesIO(data)) as source:
            if source.width <= width:
                return None
            if on_demand and source.width * source.height > ON_DEMAND_MAX_PIXELS:
                raise TooHeavy

            source.thumbnail((width, width * 4))
            out = BytesIO()
            source.convert("RGBA" if "A" in source.getbands() else "RGB").save(
                out, "WEBP", quality=82, method=4
            )
            return out.getvalue()
    except TooHeavy:
        raise
    except Exception:  # noqa: BLE001 — صورة تالفة أو Pillow غائبة: الأصل أنفع من خطأ
        return None


def render(image: DesignImage, width: int, *, on_demand: bool = False) -> tuple[str, bytes] | None:
    """يقرأ الأصل من المخزن ويكتب المصغّر في الذاكرة المؤقتة. None إن تعذّر فتح الملف أو نوعه غير معروف.

    `on_demand` (مسار الويب) يرفع `TooHeavy` للصور الثقيلة؛ والمهمة الخلفية والأمر لا يقيّدان."""
    kind = IMAGE_TYPES.get(PurePosixPath(image.file.name or "").suffix.lower())
    if kind is None:
        return None
    try:
        with image.file.open("rb") as handle:
            data = handle.read()
    except OSError:
        return None
    thumb = _resize(data, width, on_demand=on_demand)
    value = (kind, data) if thumb is None else ("image/webp", thumb)
    cache.set(_cache_key(image, width), value, THUMB_TTL)
    return value


def warm(images, *, widths: tuple[int, ...] = THUMB_WIDTHS) -> int:
    """يسخّن ما لم يكن في الذاكرة. يعيد عدد ما وُلِّد الآن."""
    made = 0
    for image in images:
        for width in widths:
            if cached(image, width) is None and render(image, width) is not None:
                made += 1
    return made
