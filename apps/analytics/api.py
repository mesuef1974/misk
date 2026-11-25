"""إشارة «عُرضت صفحة منتج» من الواجهة. العرض يُقاس من المتصفح لا من مسار القراءة: الزواحف وسكربتات القياس
تقرأ مسار التفاصيل ولا ترسل الإشارة. الإضافة للسلة وبدء الدفع يُسجَّلان في الخادم عند نجاحهما."""

from __future__ import annotations

from typing import Literal

from django.http import HttpRequest
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from ninja.utils import check_csrf

from apps.catalog import selectors as catalog_selectors
from apps.core.auth import CSRF_FAILED
from apps.core.throttling import ClientRateThrottle
from apps.designs import selectors as design_selectors

from . import services

router = Router(tags=["المتجر"], auth=None, throttle=[ClientRateThrottle("store-events", "60/m")])


class ViewIn(Schema):
    kind: Literal["design", "template"]
    slug: str = Field(min_length=1, max_length=120)


@router.post("/view", response={204: None})
def viewed(request: HttpRequest, payload: ViewIn):
    """204 دائمًا: ما ليس معروضًا للبيع لا يُسجَّل، ولا يُكشف للمرسل أيّ الأسماء موجود."""
    if check_csrf(request) is not None:
        raise HttpError(403, CSRF_FAILED)
    if payload.kind == "design":
        known = design_selectors.listed_designs().filter(slug=payload.slug).exists()
        subject = services.design_subject(payload.slug)
    else:
        known = catalog_selectors.active_templates().filter(slug=payload.slug).exists()
        subject = services.template_subject(payload.slug)
    if known:
        services.record(services.Kind.VIEW, subject)
    return Status(204, None)
