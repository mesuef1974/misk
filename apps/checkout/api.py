"""مسارات السلة والدفع: سلة ضيف بلا دخول، فتح جلسة الدفع، وإشعار المزوّد.

السلة معرّفها في جلسة Django (كوكي HttpOnly)، فكل كتابة فيها تشترط رمز CSRF وإن كانت بلا دخول.
إشعار المزوّد بلا جلسة ولا CSRF: توقيعه هو التحقق. الأخطاء بصيغة مسارات المتجر (رمز ثابت ورسالة بلغتين).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from django.http import HttpRequest
from django.utils import timezone
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from ninja.utils import check_csrf

from apps.catalog import designer
from apps.catalog import domain as catalog_domain
from apps.catalog import storefront_api as store
from apps.core.auth import CSRF_FAILED, staff_auth
from apps.core.services import record_audit
from apps.core.throttling import ClientRateThrottle
from apps.orders import services as orders_services

from . import cart, providers, selectors, services
from .models import Payment

Lang = store.Lang
SESSION_KEY = "cart_ref"

cart_router = Router(tags=["السلة والدفع"], auth=None, throttle=[ClientRateThrottle("store-cart", "60/m")])
# فتح جلسة الدفع يعيد رسم البنود ويحسب السعة: حدّه أضيق.
CHECKOUT_THROTTLE = ClientRateThrottle("store-checkout", "10/m")
payments_router = Router(tags=["الدفع"], auth=None)
WEBHOOK_THROTTLE = ClientRateThrottle("payment-webhook", "600/m")

MESSAGES: store.Messages = {
    **store.MESSAGES,
    "cart_empty": ("السلة فارغة", "Your cart is empty"),
    "cart_locked": (
        "فُتحت صفحة الدفع لهذه السلة؛ أكمل الدفع أو انتظر انتهاء مهلته",
        "Payment has started for this cart; complete it or wait for it to expire",
    ),
    "cart_full": ("السلة بلغت حدّها من البنود", "Your cart has reached its item limit"),
    "cart_expired": (
        "انتهت مهلة الدفع وأُلغي الطلب؛ ابدأ سلة جديدة",
        "The payment window expired and the order was cancelled; please start a new cart",
    ),
    "cart_changed": ("تغيّرت السلة؛ راجعها ثم أعد المحاولة", "Your cart changed; review it and try again"),
    "item_not_found": ("البند غير موجود في السلة", "Item is not in your cart"),
    "bad_quantity": (
        f"الكمية بين 1 و{cart.MAX_LINE_QUANTITY}",
        f"Quantity must be between 1 and {cart.MAX_LINE_QUANTITY}",
    ),
    "not_acknowledged": (
        "أقِرّ بمراجعة النص والتهجئة قبل الإضافة",
        "Please confirm you reviewed the text and spelling",
    ),
    "preview_mismatch": (
        "المعاينة تغيّرت؛ حدّثها ثم أضف المنتج",
        "The preview is out of date; refresh it and add the product again",
    ),
    "not_for_sale": ("هذا المنتج غير معروض للبيع الآن", "This product is not for sale right now"),
    "design_changed": (
        "تغيّر تصميم بعض البنود منذ إضافتها؛ احذفها وأضفها من جديد",
        "Some items changed since you added them; remove and add them again",
    ),
    "date_in_past": ("التاريخ مضى", "The date is in the past"),
    "no_capacity": (
        "لا مواعيد متاحة الآن؛ تواصل معنا",
        "No production slots are available right now; please contact us",
    ),
    "occasion_too_soon": (
        "لا نلحق تاريخ المناسبة؛ أقرب جاهزية مذكورة",
        "We cannot make the occasion date; the earliest ready date is shown",
    ),
    "payments_unavailable": ("الدفع غير متاح الآن", "Payment is not available right now"),
    "provider_unavailable": (
        "تعذّر فتح صفحة الدفع؛ أعد المحاولة بعد قليل",
        "Could not open the payment page; please try again shortly",
    ),
}
_CART_STATUS = {"not_found": 404, "item_not_found": 404, "cart_locked": 409}
_CHECKOUT_STATUS = {
    "cart_changed": 409,
    "cart_expired": 409,
    "payments_unavailable": 503,
    "provider_unavailable": 503,
}


class CartItemIn(Schema):
    template_slug: str = Field(min_length=1, max_length=100)
    material_id: int
    params: dict[str, Any]
    quantity: int = Field(1, ge=1, le=cart.MAX_LINE_QUANTITY)
    sha256: str = Field(min_length=64, max_length=64)
    acknowledged: bool = False  # «راجعتُ النص والتهجئة»
    lang: Lang = "ar"


class QuantityIn(Schema):
    quantity: int = Field(ge=1, le=cart.MAX_LINE_QUANTITY)
    lang: Lang = "ar"


class CartItemOut(Schema):
    id: int
    template_slug: str
    name: str
    name_en: str
    material_id: int
    material_name: str
    material_name_en: str
    params: dict[str, Any]
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    needs_review: bool


class CartOut(Schema):
    status: str  # empty | draft | awaiting_payment
    items: list[CartItemOut]
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    currency: str
    ready_on: date | None
    needs_review: bool
    payment_url: str | None


class CheckoutIn(Schema):
    customer_name: str = Field(min_length=1, max_length=services.NAME_LENGTH)
    fulfillment: str
    occasion_date: date | None = None
    notes: str = Field("", max_length=orders_services.MAX_NOTES_LENGTH)
    source: str = ""
    delivery_zone_id: int | None = None  # مطلوب مع التوصيل؛ من `/api/store/delivery-zones`
    lang: Lang = "ar"


class CheckoutOut(Schema):
    payment_url: str
    amount: Decimal
    currency: str
    expires_at: datetime
    tracking_token: str  # رابط التتبّع السري؛ يُسلَّم لصاحب الطلب عند فتح الدفع


class CheckoutErrorOut(store.ErrorOut):
    ready_on: date | None = None


class WebhookOut(Schema):
    ok: bool
    outcome: str


def _cart_ref(request: HttpRequest) -> uuid.UUID | None:
    try:
        return uuid.UUID(request.session.get(SESSION_KEY, ""))
    except (ValueError, TypeError, AttributeError):
        return None


def _require_csrf(request: HttpRequest) -> None:
    # المسار بلا auth فلا يفحص Ninja الرمز؛ نفحصه هنا لأن الكتابة تعتمد على كوكي الجلسة.
    if check_csrf(request) is not None:
        raise HttpError(403, CSRF_FAILED)


def _error(code: str, lang: Lang, **extra):
    return store.error_body(code, lang, messages=MESSAGES, **extra)


def _view(request: HttpRequest) -> dict[str, Any]:
    return selectors.cart_view(cart.find(_cart_ref(request)), now=timezone.now())


def _cart_error(exc: cart.CartError, lang: Lang):
    return Status(_CART_STATUS.get(exc.code, 422), _error(exc.code, lang))


_CART_ERRORS = {403: store.ErrorOut, 404: store.ErrorOut, 409: store.ErrorOut, 422: store.ErrorOut}


@cart_router.get("", response=CartOut)
def get_cart(request: HttpRequest):
    return _view(request)


@cart_router.post("/items", response={200: CartOut, **_CART_ERRORS})
def add_item(request: HttpRequest, payload: CartItemIn):
    _require_csrf(request)
    lang = payload.lang
    try:
        order = cart.add_item(
            cart_ref=_cart_ref(request),
            template_slug=payload.template_slug,
            material_id=payload.material_id,
            params=payload.params,
            quantity=payload.quantity,
            sha256=payload.sha256,
            acknowledged=payload.acknowledged,
        )
    except cart.CartError as exc:
        return _cart_error(exc, lang)
    except designer.DesignUnavailableError as exc:
        return Status(422, _error(exc.code, lang))
    except catalog_domain.ParamError as exc:
        fields = {name: store.param_code(message) for name, message in exc.errors.items()}
        return Status(422, _error("invalid", lang, fields=fields))
    except designer.DesignRejectedError as exc:
        return Status(422, _error("invalid", lang, fields=exc.errors, suggestions=exc.suggestions))
    request.session[SESSION_KEY] = str(order.client_ref)
    return Status(200, _view(request))


@cart_router.patch("/items/{item_id}", response={200: CartOut, **_CART_ERRORS})
def set_quantity(request: HttpRequest, item_id: int, payload: QuantityIn):
    _require_csrf(request)
    try:
        cart.set_quantity(cart_ref=_cart_ref(request), item_id=item_id, quantity=payload.quantity)
    except cart.CartError as exc:
        return _cart_error(exc, payload.lang)
    return Status(200, _view(request))


@cart_router.delete("/items/{item_id}", response={200: CartOut, **_CART_ERRORS})
def remove_item(request: HttpRequest, item_id: int, lang: Lang = "ar"):
    _require_csrf(request)
    try:
        cart.remove_item(cart_ref=_cart_ref(request), item_id=item_id)
    except cart.CartError as exc:
        return _cart_error(exc, lang)
    return Status(200, _view(request))


@cart_router.post(
    "/checkout",
    response={200: CheckoutOut, 409: CheckoutErrorOut, 422: CheckoutErrorOut, 503: CheckoutErrorOut},
    throttle=CHECKOUT_THROTTLE,
)
def checkout(request: HttpRequest, payload: CheckoutIn):
    """يفتح صفحة الدفع عند المزوّد. الطلب يصير مدفوعًا من إشعار المزوّد لا من العودة من الصفحة."""
    _require_csrf(request)
    form = services.CheckoutForm(
        customer_name=payload.customer_name,
        fulfillment=payload.fulfillment,
        occasion_date=payload.occasion_date,
        notes=payload.notes,
        source=payload.source,
        delivery_zone_id=payload.delivery_zone_id,
        lang=payload.lang,
    )
    try:
        payment = services.start_checkout(cart_ref=_cart_ref(request), form=form)
    except services.CheckoutError as exc:
        body = _error(exc.code, payload.lang, fields=exc.fields)
        return Status(_CHECKOUT_STATUS.get(exc.code, 422), {**body, "ready_on": exc.ready_on})
    return Status(
        200,
        {
            "payment_url": payment.payment_url,
            "amount": payment.amount,
            "currency": payment.currency,
            "expires_at": payment.expires_at,
            "tracking_token": payment.order.tracking_token,
        },
    )


@payments_router.post("/webhooks/{provider}", response=WebhookOut, throttle=WEBHOOK_THROTTLE)
def webhook(request: HttpRequest, provider: str):
    """الحدث المكرَّر يُجاب بـ 200 دون أثر، فإعادة الإرسال من المزوّد آمنة."""
    try:
        outcome = services.handle_webhook(provider_name=provider, body=request.body, headers=request.headers)
    except LookupError as exc:
        raise HttpError(404, "مزوّد غير معروف") from exc
    except providers.SignatureError as exc:
        # سبب الرفض لا يُفصَّل للمرسل: من لا يحمل السرّ لا يتعلّم منه شيئًا.
        raise HttpError(400, "إشعار غير موثوق") from exc
    return {"ok": True, "outcome": outcome}


@payments_router.post("/test/sessions/{session_id}/{outcome}", response=WebhookOut, auth=staff_auth)
def simulate(request: HttpRequest, session_id: str, outcome: Literal["captured", "failed"]):
    """للطاقم ومع مزوّد الاختبار وحده: يرسل إشعارًا موقَّعًا لجلسة كما ترسله البوابة، بالمسار نفسه."""
    provider = providers.active()
    if not isinstance(provider, providers.TestProvider):
        raise HttpError(404, "مزوّد الاختبار غير مفعَّل")
    payment = Payment.objects.filter(provider=provider.name, session_id=session_id).first()
    if payment is None:
        raise HttpError(404, "جلسة الدفع غير موجودة")
    now = timezone.now().timestamp()
    body, headers = provider.signed_event(
        kind=providers.CAPTURED if outcome == "captured" else providers.FAILED,
        session_id=session_id,
        amount=payment.amount,
        currency=payment.currency,
        now=now,
    )
    record_audit(
        action="payment.test_simulate",
        actor=request.user if request.user.is_authenticated else None,
        target=f"payment:{payment.pk}",
        payload={"outcome": outcome},
    )
    result = services.handle_webhook(provider_name=provider.name, body=body, headers=headers, now=now)
    return {"ok": True, "outcome": result}
