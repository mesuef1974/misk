"""كتابة السلة: طلب مسودة بقناة المتجر يعرّفه مرجع محفوظ في جلسة الزائر (كوكي HttpOnly).

كل بند يُعاد رسمه هنا من المصمِّم نفسه، وبصمة ملف القص تُثبَّت عليه: ما يراه العميل هو ما يُقصّ.
السعر من القالب في الخادم، ولا يُقبل سعر من العميل.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Any

from django.db import transaction

from apps.catalog import designer
from apps.catalog import domain as catalog_domain
from apps.catalog import selectors as catalog_selectors
from apps.catalog.models import Material
from apps.designs import selectors as design_selectors
from apps.designs import services as design_services
from apps.orders import services as orders_services
from apps.orders.models import Customer, Order, OrderItem

Status = Order.Status

# اسم مؤقت حتى يكتب العميل اسمه عند الدفع؛ الزبون صف لكل طلب فلا يختلط ضيف بضيف.
GUEST_NAME = "ضيف المتجر"
MAX_LINES = 20
MAX_LINE_QUANTITY = 50  # الكميات الأكبر طلب شركة بعرض سعر (المرحلة 3)


class CartError(Exception):
    """مخالفة لقاعدة السلة. `code` رمز ثابت تترجمه المسارات."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def find(cart_ref: uuid.UUID | None) -> Order | None:
    if cart_ref is None:
        return None
    return Order.objects.filter(client_ref=cart_ref, channel=Order.Channel.STOREFRONT).first()


def _locked(cart_ref: uuid.UUID | None) -> Order | None:
    if cart_ref is None:
        return None
    return (
        Order.objects.select_for_update()
        .filter(client_ref=cart_ref, channel=Order.Channel.STOREFRONT)
        .first()
    )


def _editable(cart_ref: uuid.UUID | None) -> Order:
    order = _locked(cart_ref)
    if order is None or order.status not in (Status.DRAFT, Status.AWAITING_PAYMENT):
        raise CartError("cart_empty")
    if order.status == Status.AWAITING_PAYMENT:
        raise CartError("cart_locked")
    return order


def _check_quantity(quantity: int) -> None:
    if not 1 <= quantity <= MAX_LINE_QUANTITY:
        raise CartError("bad_quantity")


@transaction.atomic
def add_item(
    *,
    cart_ref: uuid.UUID | None,
    template_slug: str,
    material_id: int,
    params: dict[str, Any],
    quantity: int,
    sha256: str,
    acknowledged: bool,
) -> Order:
    """يضيف بندًا ويفتح السلة إن لم تكن. يرمي أخطاء المصمِّم كما هي (`designer.*Error`، `ParamError`).

    `sha256` بصمة المعاينة التي أقرّ العميل نصّها: إن خالفت ما يرسمه الخادم الآن رُفض البند.
    """
    if not acknowledged:
        raise CartError("not_acknowledged")
    _check_quantity(quantity)
    template = catalog_selectors.template_by_slug(template_slug)
    if template is None:
        raise CartError("not_found")
    material = Material.objects.filter(pk=material_id).first()
    if material is None:
        raise CartError("material_not_offered")
    if template.base_price <= 0:
        raise CartError("not_for_sale")
    rendered = designer.render(template, material, params)
    if not hmac.compare_digest(rendered.sha256, sha256):
        raise CartError("preview_mismatch")

    order = _open(cart_ref)
    OrderItem.objects.create(
        order=order,
        template=template,
        material=material,
        params=catalog_domain.clean_params(template.param_schema, params),
        quantity=quantity,
        unit_price=template.base_price,
        svg_sha256=rendered.sha256,
        review_reasons=rendered.review_reasons,
    )
    return order


@transaction.atomic
def add_design_item(
    *,
    cart_ref: uuid.UUID | None,
    design_slug: str,
    variant_code: str,
    material_id: int,
    quantity: int,
    acknowledged: bool,
) -> Order:
    """يضيف تصميمًا جاهزًا: لا معاينة ولا بصمة معاينة، والإقرار إقرار بالمقاس والخامة.

    السعر من تقدير النسخة على المادة لحظة الإضافة، والبصمة بصمة ملف النسخة. يُرفض ما ليس منشورًا أو بلا سعر.
    """
    if not acknowledged:
        raise CartError("size_not_acknowledged")
    _check_quantity(quantity)
    found = design_selectors.offer(design_slug, variant_code, material_id)
    if found is None:
        raise CartError("not_for_sale")
    design, variant, offer = found
    price = offer.price
    if price is None:  # العرض لا يحمل إلا ما له سعر؛ الفحص للنوع
        raise CartError("not_for_sale")
    template = design_services.ensure_sale_template(design)
    order = _open(cart_ref)
    OrderItem.objects.create(
        order=order,
        template=template,
        material=offer.material,
        design_variant=variant,
        quantity=quantity,
        unit_price=price,
        svg_sha256=variant.svg_sha256,
    )
    return order


def _open(cart_ref: uuid.UUID | None) -> Order:
    """السلة التي يُضاف إليها، مقفولةً: القائمة إن كانت مسودة، وإلا سلة جديدة (لا سلة، أو دُفعت أو أُلغيت)."""
    order = _locked(cart_ref)
    if order is not None and order.status == Status.AWAITING_PAYMENT:
        raise CartError("cart_locked")
    if order is None or order.status != Status.DRAFT:
        return Order.objects.create(
            customer=Customer.objects.create(name=GUEST_NAME),
            channel=Order.Channel.STOREFRONT,
            tracking_token=orders_services.new_tracking_token(),
        )
    if order.items.count() >= MAX_LINES:
        raise CartError("cart_full")
    return order


@transaction.atomic
def set_quantity(*, cart_ref: uuid.UUID | None, item_id: int, quantity: int) -> Order:
    _check_quantity(quantity)
    order = _editable(cart_ref)
    if not order.items.filter(pk=item_id).update(quantity=quantity):
        raise CartError("item_not_found")
    return order


@transaction.atomic
def remove_item(*, cart_ref: uuid.UUID | None, item_id: int) -> Order:
    """حذف بند غير موجود لا يغيّر شيئًا (idempotent)."""
    order = _editable(cart_ref)
    order.items.filter(pk=item_id).delete()
    return order
