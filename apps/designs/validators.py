"""فحص صورة العرض المرفوعة: نقطية فقط، بتوقيعها لا بامتدادها وحده. SVG مرفوض لأنه متجه يحمل التصميم."""

from __future__ import annotations

from pathlib import PurePosixPath

from django.core.exceptions import ValidationError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
# صورة عرض لا تحتاج أكثر؛ وفك PNG بـ278 ميغابكسل يحجز >0.8 غ.ب ويرفضه Pillow (حماية فك الضغط) فيفشل بناء المصغّرات بصمت.
MAX_IMAGE_PIXELS = 50_000_000
# الامتداد ← نوع المحتوى الذي يُخدَم به.
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def sniff_image(head: bytes) -> str | None:
    """نوع المحتوى من أول 12 بايت، أو None لما ليس JPEG ولا PNG ولا WebP."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_showcase_image(upload) -> None:
    declared = IMAGE_TYPES.get(PurePosixPath(upload.name).suffix.lower())
    if declared is None:
        raise ValidationError("الصورة JPEG أو PNG أو WebP فقط")
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError("حجم الصورة يتجاوز 5 م.ب")
    position = upload.tell()
    upload.seek(0)
    head = upload.read(12)
    upload.seek(position)
    if sniff_image(head) != declared:
        raise ValidationError("محتوى الملف لا يطابق امتداده")
    _check_pixels(upload)


def _check_pixels(upload) -> None:
    """يرفض الأبعاد الهائلة من ترويسة الملف دون فك البكسلات. ما تعذّرت قراءة ترويسته يمرّ كما كان."""
    from PIL import Image  # noqa: PLC0415 — اعتمادية اختيارية

    position = upload.tell()
    upload.seek(0)
    try:
        with Image.open(upload) as image:
            pixels = image.width * image.height
    except Image.DecompressionBombError:
        pixels = MAX_IMAGE_PIXELS + 1
    except Exception:  # noqa: BLE001 — ترويسة غير مقروءة: لا يُرفض هنا ما لم يكن ثقيلًا
        return
    finally:
        upload.seek(position)
    if pixels > MAX_IMAGE_PIXELS:
        raise ValidationError(
            f"أبعاد الصورة كبيرة جدًا ({pixels / 1_000_000:.0f} ميغابكسل)؛ الحد {MAX_IMAGE_PIXELS // 1_000_000} ميغابكسل. صغّرها إلى نحو 3000 بكسل عرضًا"
        )
