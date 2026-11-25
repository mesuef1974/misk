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
