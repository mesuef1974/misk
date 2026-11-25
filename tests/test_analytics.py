"""قياس المتجر: العدّادات اليومية، وإشارة العرض العامة، وتسجيل الإضافة للسلة وبدء الدفع، وأن القياس لا يُفشل الطلب."""

from datetime import date, timedelta

import pytest
from django.db import DatabaseError
from django.test import Client
from django.utils import timezone

from apps.analytics import selectors, services
from apps.analytics.models import StoreEventCount

pytestmark = pytest.mark.django_db
Kind = StoreEventCount.Kind


def test_record_creates_then_increments_one_row_per_day_kind_subject():
    for _ in range(3):
        services.record(Kind.VIEW, "design:a")
    services.record(Kind.VIEW, "design:b")
    services.record(Kind.CHECKOUT_START)
    rows = {(r.kind, r.subject): r.count for r in StoreEventCount.objects.all()}
    assert rows == {("view", "design:a"): 3, ("view", "design:b"): 1, ("checkout_start", ""): 1}
    assert {r.day for r in StoreEventCount.objects.all()} == {timezone.localdate()}


def test_record_swallows_database_errors(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise DatabaseError("down")

    monkeypatch.setattr(services, "_bump", boom)
    services.record(Kind.VIEW, "design:a")
    assert "تعذّر تسجيل حدث المتجر" in caplog.text


def test_totals_sum_the_period_and_filter_by_subject():
    today = date(2026, 12, 1)
    for day, kind, subject, count in (
        (today, "view", "design:a", 40),
        (today - timedelta(days=1), "view", "design:b", 10),
        (today, "view", "template:t", 5),
        (today, "cart_add", "design:a", 4),
        (today - timedelta(days=9), "view", "design:a", 99),
    ):
        StoreEventCount.objects.create(day=day, kind=kind, subject=subject, count=count)
    week = selectors.totals(today - timedelta(days=6), today, subject_prefix="design:")
    assert week == {"view": 50, "cart_add": 4, "checkout_start": 0}
    assert selectors.totals(today, today)["view"] == 45
    assert selectors.rate(week["cart_add"], week["view"]) == 8.0
    assert selectors.rate(1, 0) is None


def _post_view(client: Client, kind: str, slug: str):
    return client.post(
        "/api/store/events/view", {"kind": kind, "slug": slug}, content_type="application/json"
    )


def test_view_beacon_counts_only_products_on_sale(monkeypatch):
    from apps.analytics import api

    class Listed:
        def filter(self, slug):
            self.slug = slug
            return self

        def exists(self):
            return self.slug == "gift-box"

    monkeypatch.setattr(api.design_selectors, "listed_designs", lambda: Listed())
    client = Client()
    assert _post_view(client, "design", "gift-box").status_code == 204
    assert _post_view(client, "design", "gift-box").status_code == 204
    assert _post_view(client, "design", "hidden").status_code == 204
    assert _post_view(client, "template", "no-such-template").status_code == 204
    assert {(r.kind, r.subject): r.count for r in StoreEventCount.objects.all()} == {
        ("view", "design:gift-box"): 2
    }


def test_view_beacon_validates_input_and_requires_csrf():
    client = Client()
    assert _post_view(client, "order", "x").status_code == 422
    assert _post_view(client, "design", "x" * 121).status_code == 422
    strict = Client(enforce_csrf_checks=True)
    assert _post_view(strict, "design", "gift-box").status_code == 403
    assert not StoreEventCount.objects.exists()


def _listed_design(slug: str, *, price: str, complete: bool, personalization=(), material=None):
    from decimal import Decimal

    from apps.catalog.models import Material
    from apps.designs.models import Design, DesignSource, DesignVariant, VariantEstimate

    source, _ = DesignSource.objects.get_or_create(
        name="بائع", defaults={"license_kind": DesignSource.License.COMMERCIAL}
    )
    material = (
        material
        or Material.objects.get_or_create(name="خشب", thickness_mm=Decimal("3"), defaults={"kind": "wood"})[0]
    )
    design = Design.objects.create(
        source=source,
        name_original=slug,
        slug=slug,
        status=Design.Status.APPROVED,
        is_listed=True,
        personalization=list(personalization),
    )
    variant = DesignVariant.objects.create(
        design=design,
        folder_path=slug,
        svg_sha256=slug.ljust(64, "0"),
        analysis={"operations": {"cut": {"material": "wood"}}},
        analyzed_at=timezone.now(),
    )
    VariantEstimate.objects.create(
        variant=variant, material=material, price=Decimal(price), complete=complete
    )
    return design


def test_plan_metrics_command_prints_computed_kpis_and_drops_those_without_data():
    import json
    from io import StringIO

    from django.core.management import call_command

    end = date(2026, 12, 7)
    _listed_design("plain", price="120", complete=True)
    _listed_design("named", price="150", complete=False, personalization=[{"key": "name", "type": "text"}])
    hidden = _listed_design("hidden", price="900", complete=True)
    hidden.is_listed = False
    hidden.save(update_fields=["is_listed"])
    for day, kind, subject, count in (
        (end, "view", "design:named", 40),
        (end - timedelta(days=6), "cart_add", "design:named", 6),
        (end - timedelta(days=7), "view", "design:named", 500),  # خارج الأسبوع
        (end, "view", "design:plain", 30),
        (end, "cart_add", "design:plain", 9),
        (end, "view", "design:hidden", 10),  # غير منشور: لا يدخل فئة السعر العالي
    ):
        StoreEventCount.objects.create(day=day, kind=kind, subject=subject, count=count)

    def run(*args):
        out = StringIO()
        call_command("plan_metrics", "--date", end.isoformat(), *args, stdout=out)
        return json.loads(out.getvalue())

    # نسخة من اثنتين معروضتين تقديرها مكتمل؛ 6 ÷ 40 للمخصَّص؛ لا تصميم منشور فوق 300 فيسقط I8.k1.
    assert run() == {"C0.k1": 50.0, "I1.k1": 15.0}
    assert run("--days", "8")["I1.k1"] == 1.1

    _listed_design("grand", price="450", complete=True)
    StoreEventCount.objects.create(day=end, kind="view", subject="design:grand", count=20)
    StoreEventCount.objects.create(day=end, kind="cart_add", subject="design:grand", count=1)
    assert run() == {"C0.k1": 66.7, "I1.k1": 15.0, "I8.k1": 5.0}


def test_plan_metrics_is_empty_without_listings_and_feeds_plan_ingest():
    import sys
    from pathlib import Path

    from django.conf import settings

    sys.path.insert(0, str(Path(settings.BASE_DIR) / "automation"))
    import plan as growth

    assert selectors.plan_metrics(date(2026, 12, 1), date(2026, 12, 7)) == {}
    _listed_design("only", price="80", complete=True)
    snapshot = selectors.plan_metrics(date(2026, 12, 1), date(2026, 12, 7))
    assert snapshot == {"C0.k1": 100.0}
    plan = growth.load()
    assert growth.ingest(plan, snapshot, date(2026, 12, 7)) == ["C0.k1"]
    assert growth.find_kpi(plan, "C0.k1")["value"] == 100.0
