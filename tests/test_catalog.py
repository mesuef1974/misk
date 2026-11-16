from datetime import date
from decimal import Decimal

import pytest

from apps.catalog import domain, services
from apps.catalog.models import Calibration, Material, ProductTemplate
from apps.core.models import AuditLog

NAME_SCHEMA = [
    {"name": "text", "type": "text", "max_length": 12},
    {"name": "font", "type": "choice", "choices": ["naskh", "kufi"], "required": False},
    {"name": "size", "type": "int", "min": 8, "max": 40, "required": False},
    {"name": "frame", "type": "bool", "required": False},
]


def test_clean_params_normalizes_and_keeps_schema_order():
    cleaned = domain.clean_params(NAME_SCHEMA, {"size": 12, "text": "  نور   الهدى "})
    assert cleaned == {"text": "نور الهدى", "size": 12}
    assert list(cleaned) == ["text", "size"]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({}, "text"),
        ({"text": ""}, "text"),
        ({"text": "ن" * 13}, "text"),
        ({"text": 5}, "text"),
        ({"text": "نور", "font": "thuluth"}, "font"),
        ({"text": "نور", "size": 7}, "size"),
        ({"text": "نور", "size": True}, "size"),
        ({"text": "نور", "size": "12"}, "size"),
        ({"text": "نور", "frame": 1}, "frame"),
        ({"text": "نور", "color": "red"}, "color"),
    ],
)
def test_clean_params_rejects(params, field):
    with pytest.raises(domain.ParamError) as info:
        domain.clean_params(NAME_SCHEMA, params)
    assert field in info.value.errors


def test_clean_params_rejects_non_object():
    with pytest.raises(domain.ParamError):
        domain.clean_params(NAME_SCHEMA, ["نور"])


@pytest.mark.parametrize(
    "schema",
    [
        {"name": "text"},
        [{"type": "text"}],
        [{"name": "a", "type": "color"}],
        [{"name": "a", "type": "choice", "choices": []}],
        [{"name": "a", "type": "text", "max_length": 0}],
        [{"name": "a", "type": "text"}, {"name": "a", "type": "int"}],
    ],
)
def test_validate_schema_rejects(schema):
    with pytest.raises(domain.ParamError):
        domain.validate_schema(schema)


@pytest.mark.django_db
def test_upsert_material_is_idempotent_and_audited():
    first = services.upsert_material(name="جلد  نباتي", kind="leather", thickness_mm=Decimal("2.00"))
    second = services.upsert_material(
        name="جلد نباتي", kind="leather", thickness_mm=Decimal("2.00"), sheet_cost=Decimal("45")
    )
    assert first.pk == second.pk
    assert Material.objects.count() == 1
    assert second.sheet_cost == Decimal("45")
    assert AuditLog.objects.filter(action="catalog.material.upsert").count() == 2


@pytest.mark.django_db
def test_material_defaults_to_p2s_bed():
    material = services.upsert_material(name="خشب بتولا", kind="wood", thickness_mm=Decimal("3"))
    assert (material.sheet_width_mm, material.sheet_height_mm) == (Decimal("600"), Decimal("305"))


@pytest.mark.django_db
def test_record_calibration_is_idempotent_and_validates(material):
    values = {
        "material": material,
        "operation": "engrave",
        "power_pct": 30,
        "speed_mm_s": Decimal("200"),
        "min_line_mm": Decimal("0.4"),
        "measured_on": date(2026, 11, 16),
    }
    first = services.record_calibration(**values)
    assert services.record_calibration(**values).pk == first.pk
    assert Calibration.objects.count() == 1
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.record_calibration(**{**values, "power_pct": 101})
    assert Calibration.objects.count() == 1


@pytest.mark.django_db
def test_upsert_template_rejects_bad_schema_and_saves_nothing():
    with pytest.raises(domain.ParamError):
        services.upsert_template(
            slug="bad",
            name="x",
            generator="g",
            width_mm=Decimal("10"),
            height_mm=Decimal("10"),
            param_schema=[{"name": "a", "type": "color"}],
        )
    assert not ProductTemplate.objects.exists()


@pytest.mark.django_db
def test_catalog_api_requires_staff(client, django_user_model):
    assert client.get("/api/catalog/materials").status_code == 401
    client.force_login(django_user_model.objects.create_user(username="u", password="x" * 12))
    assert client.get("/api/catalog/materials").status_code == 401


@pytest.mark.django_db
def test_catalog_api_roundtrip(client, staff_user):
    client.force_login(staff_user)
    res = client.post(
        "/api/catalog/materials",
        {"name": "جلد نباتي", "kind": "leather", "thickness_mm": "2.0"},
        content_type="application/json",
    )
    assert res.status_code == 200, res.content
    material_id = res.json()["id"]
    res = client.post(
        f"/api/catalog/materials/{material_id}/calibrations",
        {
            "operation": "engrave",
            "power_pct": 30,
            "speed_mm_s": "200",
            "min_line_mm": "0.4",
            "measured_on": "2026-11-16",
        },
        content_type="application/json",
    )
    assert res.status_code == 200, res.content
    assert len(client.get(f"/api/catalog/materials/{material_id}/calibrations").json()) == 1
    res = client.post(
        "/api/catalog/templates",
        {
            "slug": "x",
            "name": "x",
            "generator": "g",
            "width_mm": "10",
            "height_mm": "10",
            "param_schema": [{"name": "a", "type": "color"}],
        },
        content_type="application/json",
    )
    assert res.status_code == 422
    res = client.post(
        "/api/catalog/materials",
        {"name": "خشب", "kind": "stone", "thickness_mm": "2.0"},
        content_type="application/json",
    )
    assert res.status_code == 422
