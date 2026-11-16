from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(username="staff", password="x" * 12, is_staff=True)


@pytest.fixture
def material(db):
    from apps.catalog import services

    return services.upsert_material(
        name="جلد نباتي", kind="leather", thickness_mm=Decimal("2.0"), sheet_cost=Decimal("45.00")
    )


@pytest.fixture
def calibration(material):
    from apps.catalog import services

    return services.record_calibration(
        material=material,
        operation="engrave",
        power_pct=30,
        speed_mm_s=Decimal("200"),
        min_line_mm=Decimal("0.4"),
        measured_on=date(2026, 11, 16),
    )


@pytest.fixture
def name_tag(db):
    """ميدالية اسم 80 × 50 مم بحقل نص واحد."""
    from apps.catalog import services

    return services.upsert_template(
        slug="name-tag",
        name="ميدالية اسم",
        generator="name_tag",
        width_mm=Decimal("80"),
        height_mm=Decimal("50"),
        base_price=Decimal("25.00"),
        param_schema=[{"name": "text", "type": "text", "max_length": 12}],
    )
