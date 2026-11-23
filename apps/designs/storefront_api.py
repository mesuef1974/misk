"""مسارات «تصاميم جاهزة» العامة: قراءة فقط، بلا دخول وبتحديد معدل لكل عنوان.

ترخيص المصدر يمنع نشر الملف الرقمي: لا يخرج من هنا ملف تصميم ولا مساره ولا بصمته ولا اسمه الأصلي ولا اسم مصدره،
ولا كلفة المادة ولا زمن الماكينة. الصور صور عرض رفعها المالك (`DesignImage`) وحدها.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any

from django.http import FileResponse, HttpRequest
from ninja import Router, Schema, Status

from apps.catalog.storefront_api import ErrorOut, Lang, StoreMaterialOut, error_body
from apps.core.throttling import ClientRateThrottle

from . import selectors
from .models import Design, DesignVariant
from .validators import IMAGE_TYPES

router = Router(tags=["المتجر"], auth=None, throttle=[ClientRateThrottle("store-designs", "240/m")])

MESSAGES = {"not_found": ("التصميم غير موجود", "Design not found")}
IMAGE_CACHE = "public, max-age=86400"


class DesignImageOut(Schema):
    url: str
    alt: str
    alt_en: str


class DesignOut(Schema):
    slug: str
    name: str
    name_en: str
    category: str
    occasion: str
    price_from: Decimal
    image: DesignImageOut | None


class OfferOut(Schema):
    material: StoreMaterialOut
    price: Decimal


class DesignVariantOut(Schema):
    code: str
    sheet_width_mm: Decimal | None
    sheet_height_mm: Decimal | None
    offers: list[OfferOut]


class DesignDetailOut(DesignOut):
    description: str
    description_en: str
    assembled_width_mm: Decimal | None
    assembled_height_mm: Decimal | None
    assembled_depth_mm: Decimal | None
    images: list[DesignImageOut]
    variants: list[DesignVariantOut]
    fields: list[dict[str, Any]]  # حقول التخصيص بمخطط القالب؛ فارغة لما لا يُخصَّص


def _images(design: Design) -> list[dict]:
    return [
        {
            "url": f"/api/store/designs/{design.slug}/images/{image.pk}",
            "alt": image.alt_ar or design.name_ar,
            "alt_en": image.alt_en or design.name_en,
        }
        for image in design.images.all()
    ]


def _variants(design: Design) -> list[dict]:
    out = []
    for variant in design.variants.all():
        rows = selectors.offers(variant)
        if rows:
            out.append({"variant": variant, "offers": rows})
    return out


def _summary(design: Design) -> dict:
    images = _images(design)
    prices = [row.price for entry in _variants(design) for row in entry["offers"]]
    return {
        "slug": design.slug,
        "name": design.name_ar,
        "name_en": design.name_en,
        "category": design.category,
        "occasion": design.occasion,
        "price_from": min(prices),
        "image": images[0] if images else None,
    }


def _variant_out(variant: DesignVariant, rows: list) -> dict:
    return {
        "code": variant.code,
        "sheet_width_mm": variant.sheet_width_mm,
        "sheet_height_mm": variant.sheet_height_mm,
        "offers": [{"material": row.material, "price": row.price} for row in rows],
    }


@router.get("", response=list[DesignOut])
def list_designs(request: HttpRequest, category: str = ""):
    designs = selectors.listed_designs()
    if category:
        designs = designs.filter(category=category)
    # تصميم كل نسخه متعددة المواد له تقدير بسعر ولا عرض: يسقط هنا لا في الاستعلام.
    return [_summary(design) for design in designs if _variants(design)]


@router.get("/{slug}", response={200: DesignDetailOut, 404: ErrorOut})
def design_detail(request: HttpRequest, slug: str, lang: Lang = "ar"):
    design = selectors.listed_designs().filter(slug=slug).first()
    variants = _variants(design) if design else []
    if design is None or not variants:
        return Status(404, error_body("not_found", lang, messages=MESSAGES))
    return Status(
        200,
        {
            **_summary(design),
            "description": design.description,
            "description_en": design.description_en,
            "assembled_width_mm": design.assembled_width_mm,
            "assembled_height_mm": design.assembled_height_mm,
            "assembled_depth_mm": design.assembled_depth_mm,
            "images": _images(design),
            "fields": design.personalization,
            "variants": [_variant_out(entry["variant"], entry["offers"]) for entry in variants],
        },
    )


@router.get("/{slug}/images/{image_id}", response={404: ErrorOut})
def design_image(request: HttpRequest, slug: str, image_id: int):
    """صورة عرض لتصميم منشور وحده. النوع من الامتداد الذي فُحص توقيعه عند الرفع، لا من تخمين المتصفح."""
    missing = Status(404, error_body("not_found", "ar", messages=MESSAGES))
    design = selectors.listed_designs().filter(slug=slug).first()
    image = next((row for row in design.images.all() if row.pk == image_id), None) if design else None
    if image is None:
        return missing
    content_type = IMAGE_TYPES.get(PurePosixPath(image.file.name or "").suffix.lower())
    if content_type is None:
        return missing
    try:
        handle = image.file.open("rb")
    except OSError:
        return missing
    response = FileResponse(handle, content_type=content_type)
    response.headers["Cache-Control"] = IMAGE_CACHE
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
