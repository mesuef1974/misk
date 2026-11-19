import uuid
from decimal import Decimal

import pytest

from apps.core.models import AuditLog
from apps.orders import selectors, services
from apps.orders.models import Customer, Order, OrderItem


def _item(material, **overrides):
    values = {"template_slug": "name-tag", "material_id": material.pk, "params": {"text": "نور"}}
    return services.ItemInput(**{**values, **overrides})


def _order(material, **overrides):
    values = {"client_ref": uuid.uuid4(), "customer_name": "زبون تجريبي", "items": [_item(material)]}
    return services.create_order(**{**values, **overrides})


@pytest.mark.django_db
def test_create_order_is_idempotent_on_client_ref(material, name_tag):
    ref = uuid.uuid4()
    first = _order(material, client_ref=ref)
    second = _order(material, client_ref=ref, customer_name="اسم آخر")
    assert first.pk == second.pk
    assert (Order.objects.count(), Customer.objects.count(), OrderItem.objects.count()) == (1, 1, 1)
    assert AuditLog.objects.filter(action="orders.create").count() == 1


@pytest.mark.django_db
def test_create_order_cleans_params_and_defaults_price(material, name_tag):
    order = _order(
        material,
        items=[
            _item(material, params={"text": "  نور   الهدى "}, quantity=3),
            _item(material, unit_price=Decimal("10.50"), quantity=2),
        ],
    )
    first, second = order.items.all()
    assert first.params == {"text": "نور الهدى"}
    assert first.unit_price == Decimal("25.00")
    assert selectors.order(order.pk).total == Decimal("96.00")  # 3 × 25 + 2 × 10.50


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"items": []},
        {"customer_name": "   "},
        {"items": "bad-template"},
        {"items": "bad-material"},
        {"items": "bad-params"},
        {"items": "bad-quantity"},
        {"items": "bad-price"},
    ],
)
def test_create_order_rejects_and_saves_nothing(material, name_tag, overrides):
    bad = {
        "bad-template": {"template_slug": "missing"},
        "bad-material": {"material_id": 999_999},
        "bad-params": {"params": {"text": "ن" * 13}},
        "bad-quantity": {"quantity": 0},
        "bad-price": {"unit_price": Decimal("-1")},
    }
    if isinstance(overrides.get("items"), str):
        overrides = {"items": [_item(material), _item(material, **bad[overrides["items"]])]}
    with pytest.raises(services.OrderError):
        _order(material, **overrides)
    assert not Order.objects.exists()
    assert not Customer.objects.exists()


@pytest.mark.django_db
def test_inactive_template_cannot_be_ordered(material, name_tag):
    name_tag.is_active = False
    name_tag.save()
    with pytest.raises(services.OrderError):
        _order(material)


@pytest.mark.django_db
def test_confirm_requires_calibrated_material(material, name_tag):
    order = _order(material)
    with pytest.raises(services.OrderError, match="معايرة"):
        services.transition(order_id=order.pk, to_status="confirmed")
    order.refresh_from_db()
    assert order.status == "draft"


@pytest.mark.django_db
def test_transitions_follow_the_map(material, name_tag, calibration):
    order = _order(material)
    for status in ("confirmed", "in_production"):
        assert services.transition(order_id=order.pk, to_status=status).status == status
    with pytest.raises(services.OrderError, match="قصّ"):  # «جاهز» بعد القصّ: tests/test_production.py
        services.transition(order_id=order.pk, to_status="ready")
    for status in ("draft", "confirmed", "delivered"):
        with pytest.raises(services.OrderError):
            services.transition(order_id=order.pk, to_status=status)
    order.refresh_from_db()
    assert order.status == "in_production"


@pytest.mark.django_db
def test_transition_cannot_skip_and_same_status_is_noop(material, name_tag, calibration):
    order = _order(material)
    with pytest.raises(services.OrderError):
        services.transition(order_id=order.pk, to_status="ready")
    services.transition(order_id=order.pk, to_status="confirmed")
    services.transition(order_id=order.pk, to_status="confirmed")
    assert AuditLog.objects.filter(action="orders.transition").count() == 1


@pytest.mark.django_db
def test_orders_api(client, staff_user, material, name_tag, calibration):
    assert client.get("/api/orders").status_code == 401
    client.force_login(staff_user)
    body = {
        "client_ref": str(uuid.uuid4()),
        "customer_name": "زبون تجريبي",
        "notes": "تغليف هدية",
        "items": [
            {
                "template_slug": "name-tag",
                "material_id": material.pk,
                "params": {"text": "نور"},
                "quantity": 2,
            }
        ],
    }
    res = client.post("/api/orders", body, content_type="application/json")
    assert res.status_code == 200, res.content
    data = res.json()
    assert Decimal(data["total"]) == Decimal("50.00")
    assert data["items"][0]["template_slug"] == "name-tag"
    assert client.post("/api/orders", body, content_type="application/json").json()["id"] == data["id"]
    assert data["notes"] == "تغليف هدية"

    detail = client.get(f"/api/orders/{data['id']}")
    assert detail.status_code == 200
    assert detail.json() == data
    assert client.get("/api/orders/999999").status_code == 404

    url = f"/api/orders/{data['id']}/transition"
    assert client.post(url, {"to_status": "ready"}, content_type="application/json").status_code == 409
    assert client.post(url, {"to_status": "nope"}, content_type="application/json").status_code == 422
    res = client.post(url, {"to_status": "confirmed"}, content_type="application/json")
    assert res.json()["status"] == "confirmed"
    confirmed = client.get("/api/orders?status=confirmed").json()
    assert [row["id"] for row in confirmed["items"]] == [data["id"]]
    assert (confirmed["count"], confirmed["counts"]) == (1, {"confirmed": 1})
    drafts = client.get("/api/orders?status=draft").json()
    assert (drafts["items"], drafts["count"], drafts["counts"]) == ([], 0, {"confirmed": 1})
    assert (
        client.post(
            "/api/orders/999999/transition", {"to_status": "confirmed"}, content_type="application/json"
        ).status_code
        == 404
    )

    body["client_ref"] = str(uuid.uuid4())
    body["items"][0]["params"] = {"text": "ن" * 13}
    assert client.post("/api/orders", body, content_type="application/json").status_code == 422


@pytest.mark.django_db
def test_order_list_query_count_is_constant(material, name_tag, django_assert_max_num_queries):
    for _ in range(5):
        _order(material, items=[_item(material), _item(material)])
    with django_assert_max_num_queries(4):
        for order in selectors.orders():
            assert order.customer.name
            assert [item.template.slug for item in order.items.all()]


@pytest.mark.django_db
def test_order_detail_is_staff_only_and_constant_queries(
    client, staff_user, django_user_model, material, name_tag, django_assert_max_num_queries
):
    order = _order(material, items=[_item(material), _item(material), _item(material)])
    url = f"/api/orders/{order.pk}"
    assert client.get(url).status_code == 401
    client.force_login(django_user_model.objects.create_user(username="u", password="x" * 12))
    assert client.get(url).status_code == 401
    client.force_login(staff_user)
    with django_assert_max_num_queries(6):  # جلسة + مستخدم + الطلب + بنود + قوالب + مواد
        assert len(client.get(url).json()["items"]) == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"customer_name": "ن" * 121},
        {"notes": "م" * 2001},
        {"items": "too-many"},
        {"items": {"quantity": 1001}},
        {"items": {"quantity": 10**12}},
        {"items": {"unit_price": Decimal("10.505")}},
        {"items": {"unit_price": Decimal("1000000")}},
        {"items": {"unit_price": Decimal("NaN")}},
        {"items": {"unit_price": Decimal("Infinity")}},
    ],
)
def test_create_order_enforces_field_bounds(material, name_tag, overrides):
    items = overrides.get("items")
    if items == "too-many":
        overrides = {"items": [_item(material)] * 101}
    elif items:
        overrides = {"items": [_item(material, **items)]}
    with pytest.raises(services.OrderError):
        _order(material, **overrides)
    assert not Order.objects.exists()
    assert not Customer.objects.exists()


@pytest.mark.django_db
def test_create_order_accepts_values_at_the_bounds(material, name_tag):
    order = _order(
        material,
        customer_name="ن" * 120,
        notes="م" * 2000,
        items=[_item(material, quantity=1000, unit_price=Decimal("999999.99"))],
    )
    assert order.items.get().unit_price == Decimal("999999.99")


@pytest.mark.django_db
def test_orders_api_rejects_out_of_bounds_payload(client, staff_user, material, name_tag):
    client.force_login(staff_user)
    item = {"template_slug": "name-tag", "material_id": material.pk, "params": {"text": "نور"}}

    def post(**changes):
        body = {"client_ref": str(uuid.uuid4()), "customer_name": "زبون", "items": [item], **changes}
        return client.post("/api/orders", body, content_type="application/json").status_code

    assert post() == 200
    assert post(customer_name="ن" * 121) == 422
    assert post(notes="م" * 2001) == 422
    assert post(items=[]) == 422
    assert post(items=[item] * 101) == 422
    assert post(items=[{**item, "quantity": 10**12}]) == 422
    assert post(items=[{**item, "quantity": 0}]) == 422
    assert post(items=[{**item, "unit_price": "10.505"}]) == 422
    assert post(items=[{**item, "unit_price": "-1"}]) == 422
    assert post(items=[{**item, "unit_price": "12345678.00"}]) == 422
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_same_customer_name_does_not_merge_two_people(material, name_tag):
    """الاسم لا يميّز شخصين: طلبان بالاسم نفسه لا يُنسبان إلى زبون واحد."""
    first = _order(material, customer_name="أم  خالد")
    second = _order(material, customer_name=" أم خالد ")
    assert first.customer_id != second.customer_id
    assert first.customer.name == second.customer.name == "أم خالد"
    assert Customer.objects.count() == 2


@pytest.mark.django_db
def test_create_order_survives_concurrent_duplicate(material, name_tag, monkeypatch):
    """طلب متزامن بالـ client_ref نفسه أدرج بعد فحص الوجود: يُعاد طلبه بلا 500 ولا صفوف زائدة."""
    winner = _order(material)
    real, calls = services._existing_order, []

    def racing(client_ref):
        calls.append(client_ref)
        return None if len(calls) == 1 else real(client_ref)

    monkeypatch.setattr(services, "_existing_order", racing)
    again = _order(material, client_ref=winner.client_ref, customer_name="زبون لم يُنشأ")
    assert again.pk == winner.pk
    assert len(calls) == 2
    assert (Order.objects.count(), Customer.objects.count(), OrderItem.objects.count()) == (1, 1, 1)
    assert AuditLog.objects.filter(action="orders.create").count() == 1


@pytest.mark.django_db
def test_orders_list_is_paginated(client, staff_user, material, name_tag, django_assert_max_num_queries):
    """الصفحة تجلب `limit` طلبًا لا الجدول كله، والعدّ للجدول كله، بعدد استعلامات لا يتبع عدد الطلبات."""
    ids = [_order(material).pk for _ in range(5)]
    client.force_login(staff_user)
    with django_assert_max_num_queries(8):
        first = client.get("/api/orders?limit=2").json()
    second = client.get("/api/orders?limit=2&offset=2").json()
    last = client.get("/api/orders?limit=2&offset=4").json()
    seen = [row["id"] for page in (first, second, last) for row in page["items"]]
    assert seen == sorted(ids, reverse=True)  # الأحدث أولًا، بلا تكرار ولا إسقاط
    assert first["count"] == 5 and first["counts"] == {"draft": 5}
    assert len(client.get("/api/orders").json()["items"]) == 5
    for bad in ("limit=0", "limit=201", "offset=-1", "limit=x"):
        assert client.get(f"/api/orders?{bad}").status_code == 422


@pytest.mark.django_db
def test_admin_locks_items_once_order_leaves_draft(rf, material, name_tag, calibration, django_user_model):
    from django.contrib.admin.sites import site

    from apps.orders.admin import OrderItemInline

    request = rf.get("/")
    request.user = django_user_model.objects.create_superuser(username="root", password="x" * 12)
    inline = OrderItemInline(Order, site)
    order = _order(material)
    assert inline.has_change_permission(request, order) and inline.has_add_permission(request, order)
    assert inline.has_delete_permission(request, order)
    order = services.transition(order_id=order.pk, to_status="confirmed")
    assert not inline.has_change_permission(request, order)
    assert not inline.has_add_permission(request, order)
    assert not inline.has_delete_permission(request, order)
