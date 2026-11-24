"""مصغّرات صور عرض التصاميم الجاهزة: تُبنى مرة واحدة بعد الرفع وتُحفظ في التخزين بجوار الأصل.

لا Pillow ولا ذاكرة مؤقتة في مسار الطلب: الواجهة تخدم الملف الجاهز. البناء idempotent: تُبنى المصغّرات
ما دامت لا تطابق اسم الملف الأصلي الحالي ونسخة البناء (`thumbs_for`)، فاستبدال الأصل يعيد بناءها وإعادة المهمة آمنة."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import PurePosixPath

from django.core.cache import cache
from django.core.files.base import ContentFile

from .models import DesignImage
from .validators import IMAGE_TYPES

CACHE_TTL = 7 * 24 * 3600
CACHE_MAX_BYTES = 2 * 1024 * 1024  # أكبر من هذا يُقرأ من التخزين كل مرة بدل حجز ذاكرة Redis
THUMB_WIDTHS = (480, 960)  # البطاقة والمعرض؛ نسخة الواجهة في DesignCard.vue وDesignPage.vue
# نسخة طريقة البناء: رفعها يعيد بناء ما بُني بطريقة أقدم (الأمر build_design_thumbs) وتُخدَم القديمة ريثما يحدث ذلك.
THUMB_VERSION = 2
# الجودة تنزل درجات حتى يبلغ الملف هذا الحجم: صور النقوش الدقيقة تبلغ 700 ك.ب بجودة ثابتة 82، وزمنها زمن نقل.
QUALITY_STEPS = (80, 65, 50)
TARGET_BYTES = 150 * 1024


def thumb_field(image: DesignImage, width: int):
    return getattr(image, f"thumb_{width}")


def _source_tag(name: str | None) -> str:
    return f"{name}#{THUMB_VERSION}"


def is_current(image: DesignImage) -> bool:
    """المصغّرات كلها موجودة ومبنية من الأصل الحالي (بأي نسخة بناء): صالحة للخدمة."""
    return bool(
        image.thumbs_for.rpartition("#")[0] == image.file.name
        and all(thumb_field(image, w) for w in THUMB_WIDTHS)
    )


def is_latest(image: DesignImage) -> bool:
    """مبنية من الأصل الحالي بنسخة البناء الحالية: لا حاجة لإعادة البناء."""
    return is_current(image) and image.thumbs_for == _source_tag(image.file.name)


def etag(image: DesignImage, width: int) -> str:
    """بصمة الملف المخدوم: اسمه، فاستبدال الملف يبطل التخزين في المتصفح."""
    name = thumb_field(image, width).name if width else image.file.name
    return f'"{hashlib.sha256(f"{image.pk}:{name}".encode()).hexdigest()[:20]}"'


def body(image: DesignImage, width: int) -> bytes:
    """بايتات المصغّر الجاهز: من Redis، وإلا من التخزين ثم تُحفظ. المفتاح من اسم الملف فاستبداله يبطله.

    Redis طبقة تسريع لا مصدر حقيقة: ضياعها يعيد القراءة من التخزين. يرفع OSError إن غاب الملف."""
    key = f"design-thumb:{etag(image, width).strip(chr(34))}"
    data = cache.get(key)
    if data is None:
        with thumb_field(image, width).open("rb") as handle:
            data = handle.read()
        if len(data) <= CACHE_MAX_BYTES:
            cache.set(key, data, CACHE_TTL)
    return data


def _resize(data: bytes, width: int) -> bytes | None:
    """WebP بعرض `width` على الأكثر (بلا تكبير)، أو None إن تعذّرت القراءة."""
    try:
        from PIL import Image  # noqa: PLC0415 — اعتمادية اختيارية: بدونها يُخدَم الأصل

        with Image.open(BytesIO(data)) as source:
            source.thumbnail((width, width * 4))
            flat = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            for quality in QUALITY_STEPS:
                out = BytesIO()
                flat.save(out, "WEBP", quality=quality, method=4)
                if out.tell() <= TARGET_BYTES:
                    break
            return out.getvalue()
    except Exception:  # noqa: BLE001 — صورة تالفة أو Pillow غائبة: الأصل أنفع من خطأ
        return None


def build(image: DesignImage) -> bool:
    """يبني المصغّرات ويحفظها. يعيد True إن بُني شيء الآن. يعمل في العامل لا في الويب (فك الصور الضخمة ثقيل)."""
    if is_latest(image) or PurePosixPath(image.file.name or "").suffix.lower() not in IMAGE_TYPES:
        return False
    try:
        with image.file.open("rb") as handle:
            data = handle.read()
    except OSError:
        return False
    stamp = hashlib.sha256(_source_tag(image.file.name).encode()).hexdigest()[:8]
    made = {}
    for width in THUMB_WIDTHS:
        body = _resize(data, width)
        if body is None:
            return False
        made[width] = (f"{image.pk}-{stamp}-{width}.webp", body)
    for width, (name, body) in made.items():
        thumb_field(image, width).save(name, ContentFile(body), save=False)
    # update لا save: حفظ النموذج يطلق الإشارة فيعيد جدولة المهمة بلا نهاية.
    DesignImage.objects.filter(pk=image.pk).update(
        thumb_480=image.thumb_480.name,
        thumb_960=image.thumb_960.name,
        thumbs_for=_source_tag(image.file.name),
    )
    return True


def build_missing() -> int:
    """يبني ما ينقصه مصغّر من كل الصور (ملء رجعي بعد النشر). يعيد عدد الصور التي بُنيت."""
    return sum(build(image) for image in DesignImage.objects.all() if not is_latest(image))
