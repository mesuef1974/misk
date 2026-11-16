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
    for status in ("confirmed", "in_production", "ready", "delivered"):
        assert services.transition(order_id=order.pk, to_status=status).status == status
    for status in ("draft", "confirmed", "cancelled"):
        with pytest.raises(services.OrderError):
            services.transition(order_id=order.pk, to_status=status)


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

    url = f"/api/orders/{data['id']}/transition"
    assert client.post(url, {"to_status": "ready"}, content_type="application/json").status_code == 409
    assert client.post(url, {"to_status": "nope"}, content_type="application/json").status_code == 422
    res = client.post(url, {"to_status": "confirmed"}, content_type="application/json")
    assert res.json()["status"] == "confirmed"
    assert len(client.get("/api/orders?status=confirmed").json()) == 1
    assert client.get("/api/orders?status=draft").json() == []
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
