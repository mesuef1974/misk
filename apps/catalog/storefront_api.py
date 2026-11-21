"""مسارات المتجر العامة: الكتالوج والمصمِّم، بلا دخول وبتحديد معدل لكل عنوان.

قراءة وحساب فقط: لا تكتب ولا تقرأ جلسة، فلا CSRF يلزمها. لا تكشف مفتاح المولّد ولا كلفة الخامة.
الرسائل بلغة الطلب (`lang`)، ورمز الخطأ ثابت تعتمد عليه الواجهة.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from django.http import HttpRequest
from ninja import Query, Router, Schema, Status

from apps.core.throttling import ClientRateThrottle

from . import designer, domain, selectors
from .models import Material, ProductTemplate

Lang = Literal["ar", "en"]

router = Router(tags=["المتجر"], auth=None, throttle=[ClientRateThrottle("store", "120/m")])
# المعاينة تشكّل نصًّا وترسم هندسة: حدّها أضيق من التصفح.
PREVIEW_THROTTLE = ClientRateThrottle("store-preview", "30/m")

MESSAGES: dict[str, tuple[str, str]] = {  # (عربي، إنجليزي)
    "not_found": ("القالب غير موجود", "Product not found"),
    "no_generator": ("هذا المنتج غير متاح للتصميم الآن", "This product cannot be designed right now"),
    "material_not_offered": (
        "هذه الخامة غير متاحة لهذا المنتج",
        "This material is not available for this product",
    ),
    "invalid": ("راجع الحقول المحدّدة", "Please review the highlighted fields"),
    "required": ("مطلوب", "Required"),
    "too_long": ("النص أطول من المسموح", "Text is longer than allowed"),
    "invalid_choice": ("ليست من الخيارات", "Not one of the options"),
    "unknown_field": ("حقل غير معرَّف في القالب", "Unknown field"),
    "invalid_value": ("قيمة غير صالحة", "Invalid value"),
    "one_letter": ("اكتب حرفًا واحدًا", "Enter a single letter"),
    "two_letters": ("اكتب حرفين على الأكثر", "Enter at most two letters"),
    "unsupported_char": (
        "في النص رمز لا يحمله الخط؛ احذف الرموز والوجوه التعبيرية",
        "The text has a character this font cannot draw; remove symbols and emoji",
    ),
    "too_small": (
        "النص أطول مما يُحفر بوضوح على هذه الخامة؛ اختصره أو اختر خامة أخرى",
        "The text is too long to engrave clearly on this material; shorten it or pick another material",
    ),
    "offensive": ("لا نحفر هذا النص", "We cannot engrave this text"),
    "religious_not_allowed": (
        "نحفر النصوص الدينية على ما يُعلَّق ويُصان فقط، صونًا لها. اختر أحد المنتجات المقترحة",
        "Out of respect, we engrave religious text only on items made to be hung and kept. "
        "Please choose one of the suggested products",
    ),
}
_PARAM_CODES = {
    "مطلوب": "required",
    "ليست من الخيارات": "invalid_choice",
    "حقل غير معرَّف في القالب": "unknown_field",
}


class StoreMaterialOut(Schema):
    id: int
    name: str
    name_en: str
    kind: str
    thickness_mm: Decimal


class StoreTemplateOut(Schema):
    slug: str
    name: str
    name_en: str
    description: str
    description_en: str
    width_mm: Decimal
    height_mm: Decimal
    base_price: Decimal
    allows_religious_text: bool
    fields: list[dict[str, Any]]


class StoreTemplateDetailOut(StoreTemplateOut):
    materials: list[StoreMaterialOut]


class LimitOut(Schema):
    field: str
    when: dict[str, Any]
    max_chars: int
    min_text_height_mm: float


class PreviewIn(Schema):
    material_id: int
    params: dict[str, Any]
    lang: Lang = "ar"


class PreviewOut(Schema):
    svg: str
    sha256: str
    width_mm: float
    height_mm: float
    needs_review: bool
    review_reasons: list[str]
    text_sizes: dict[str, float]


class FieldErrorOut(Schema):
    code: str
    message: str


class ErrorOut(Schema):
    code: str
    detail: str
    fields: dict[str, FieldErrorOut] = {}
    suggestions: list[str] = []


Messages = dict[str, tuple[str, str]]


def message_text(code: str, lang: Lang, messages: Messages = MESSAGES) -> str:
    ar, en = messages.get(code, MESSAGES["invalid_value"])
    return en if lang == "en" else ar


def error_body(
    code: str,
    lang: Lang,
    *,
    fields: dict[str, str] | None = None,
    suggestions: list[str] | None = None,
    messages: Messages = MESSAGES,
) -> dict[str, Any]:
    """جسم الخطأ الموحَّد لمسارات المتجر. `messages` جدول المسار المستدعي إن زاد رموزًا على هذا."""
    return {
        "code": code,
        "detail": message_text(code, lang, messages),
        "fields": {
            name: {"code": c, "message": message_text(c, lang, messages)}
            for name, c in (fields or {}).items()
        },
        "suggestions": suggestions or [],
    }


def param_code(message: str) -> str:
    if message.startswith("أطول من"):
        return "too_long"
    return _PARAM_CODES.get(message, "invalid_value")


def _template_out(template: ProductTemplate) -> dict[str, Any]:
    return {
        "slug": template.slug,
        "name": template.name,
        "name_en": template.name_en,
        "description": template.description,
        "description_en": template.description_en,
        "width_mm": template.width_mm,
        "height_mm": template.height_mm,
        "base_price": template.base_price,
        "allows_religious_text": template.allows_religious_text,
        "fields": template.param_schema,
    }


@router.get("/templates", response=list[StoreTemplateOut])
def list_templates(request: HttpRequest):
    return [_template_out(template) for template in selectors.active_templates()]


@router.get("/templates/{slug}", response={200: StoreTemplateDetailOut, 404: ErrorOut})
def template_detail(request: HttpRequest, slug: str, lang: Lang = "ar"):
    template = selectors.template_by_slug(slug)
    if template is None:
        return Status(404, error_body("not_found", lang))
    return Status(
        200, {**_template_out(template), "materials": list(selectors.storefront_materials(template))}
    )


@router.get("/templates/{slug}/limits", response={200: list[LimitOut], 404: ErrorOut, 422: ErrorOut})
def template_limits(request: HttpRequest, slug: str, material_id: int = Query(...), lang: Lang = "ar"):
    template = selectors.template_by_slug(slug)
    material = Material.objects.filter(pk=material_id).first()
    if template is None:
        return Status(404, error_body("not_found", lang))
    if material is None:
        return Status(422, error_body("material_not_offered", lang))
    try:
        return Status(200, designer.limits(template, material))
    except designer.DesignUnavailableError as exc:
        return Status(422, error_body(exc.code, lang))


@router.post(
    "/templates/{slug}/preview",
    response={200: PreviewOut, 404: ErrorOut, 422: ErrorOut},
    throttle=PREVIEW_THROTTLE,
)
def preview(request: HttpRequest, slug: str, payload: PreviewIn):
    """ما يعود هنا هو ملف القص نفسه؛ بصمته `sha256` تُثبَّت على بند الطلب عند الإضافة للسلة."""
    lang = payload.lang
    template = selectors.template_by_slug(slug)
    material = Material.objects.filter(pk=payload.material_id).first()
    if template is None:
        return Status(404, error_body("not_found", lang))
    if material is None:
        return Status(422, error_body("material_not_offered", lang))
    try:
        return Status(200, designer.render(template, material, payload.params))
    except designer.DesignUnavailableError as exc:
        return Status(422, error_body(exc.code, lang))
    except domain.ParamError as exc:
        return Status(
            422, error_body("invalid", lang, fields={k: param_code(v) for k, v in exc.errors.items()})
        )
    except designer.DesignRejectedError as exc:
        return Status(422, error_body("invalid", lang, fields=exc.errors, suggestions=exc.suggestions))
