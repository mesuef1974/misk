import uuid
from decimal import Decimal

import pytest

from apps.orders import services as order_services
from apps.production import domain, services, tasks
from apps.production.models import Placement, RunLog, Sheet

BED = {"sheet_width": 6000, "sheet_height": 3050, "margin": 50, "gap": 30}


def _pieces(count, width=800, height=500):
    return [domain.Piece((1, index), width, height) for index in range(count)]


def _overlap(a, b):
    return a.x < b.x + b.width and b.x < a.x + a.width and a.y < b.y + b.height and b.y < a.y + a.height


def test_pack_fills_shelves_inside_margins_without_overlap():
    placed = domain.pack(_pieces(40), **BED)
    # 80 × 50 مم على 600 × 305: 7 في الرف (5 + 7×80 + 6×3 = 583) و5 رفوف (5 + 5×50 + 4×3 = 267) = 35 للوح
    assert [sum(1 for p in placed if p.sheet == s) for s in (0, 1)] == [35, 5]
    for p in placed:
        assert p.x >= 50 and p.y >= 50
        assert p.x + p.width <= 6000 - 50 and p.y + p.height <= 3050 - 50
    for sheet in (0, 1):
        on_sheet = [p for p in placed if p.sheet == sheet]
        assert not any(_overlap(a, b) for i, a in enumerate(on_sheet) for b in on_sheet[i + 1 :])
    gaps = sorted(p.x for p in placed if p.sheet == 0 and p.y == 50)
    assert all(b - a == 830 for a, b in zip(gaps, gaps[1:]))


def test_pack_is_deterministic_and_keeps_every_piece():
    mixed = [domain.Piece((i, 0), 300 + 70 * (i % 5), 200 + 90 * (i % 4)) for i in range(60)]
    first = domain.pack(mixed, **BED)
    assert first == domain.pack(list(reversed(mixed)), **BED)
    assert sorted(p.key for p in first) == sorted(p.key for p in mixed)
    for sheet in {p.sheet for p in first}:
        on_sheet = [p for p in first if p.sheet == sheet]
        assert not any(_overlap(a, b) for i, a in enumerate(on_sheet) for b in on_sheet[i + 1 :])


def test_pack_exact_fit_and_too_large():
    assert domain.pack([domain.Piece((1, 0), 5900, 2950)], **BED)[0].sheet == 0
    with pytest.raises(domain.PackingError):
        domain.pack([domain.Piece((1, 0), 5901, 2950)], **BED)
    with pytest.raises(domain.PackingError):
        domain.pack([domain.Piece((1, 0), 0, 10)], **BED)
    assert domain.pack([], **BED) == []


def _confirmed_order(material, quantity):
    order = order_services.create_order(
        client_ref=uuid.uuid4(),
        customer_name="زبون تجريبي",
        items=[
            order_services.ItemInput(
                template_slug="name-tag", material_id=material.pk, params={"text": "نور"}, quantity=quantity
            )
        ],
    )
    return order_services.transition(order_id=order.pk, to_status="confirmed")


@pytest.mark.django_db
def test_plan_sheets_places_every_copy_once(material, name_tag, calibration):
    order = _confirmed_order(material, 40)
    sheets = services.plan_sheets(material_id=material.pk)
    assert len(sheets) == 2
    assert Placement.objects.count() == 40
    assert set(Placement.objects.values_list("order_item_id", flat=True)) == {order.items.get().pk}
    first = Placement.objects.filter(sheet=sheets[0]).order_by("y_mm", "x_mm").first()
    assert (first.x_mm, first.y_mm, first.width_mm, first.height_mm) == (5, 5, 80, 50)

    assert services.plan_sheets(material_id=material.pk) == []
    assert (Sheet.objects.count(), Placement.objects.count()) == (2, 40)

    _confirmed_order(material, 3)
    assert len(services.plan_sheets(material_id=material.pk)) == 1
    assert Placement.objects.count() == 43


@pytest.mark.django_db
def test_plan_sheets_ignores_unconfirmed_and_other_materials(material, name_tag, calibration):
    order_services.create_order(
        client_ref=uuid.uuid4(),
        customer_name="مسودة",
        items=[
            order_services.ItemInput(
                template_slug="name-tag", material_id=material.pk, params={"text": "نور"}
            )
        ],
    )
    assert services.plan_sheets(material_id=material.pk) == []
    assert not Sheet.objects.exists()


@pytest.mark.django_db
def test_plan_sheets_rejects_oversized_template_and_saves_nothing(material, name_tag, calibration):
    name_tag.width_mm = Decimal("700")
    name_tag.save()
    _confirmed_order(material, 1)
    with pytest.raises(services.ProductionError):
        services.plan_sheets(material_id=material.pk)
    assert not Sheet.objects.exists()


@pytest.mark.django_db
def test_plan_task_runs_eagerly(material, name_tag, calibration):
    _confirmed_order(material, 2)
    sheet_ids = tasks.plan_sheets_async.delay(material_id=material.pk).get()
    assert list(Sheet.objects.values_list("pk", flat=True)) == sheet_ids


@pytest.mark.django_db
def test_record_run_snapshots_and_is_idempotent(material, name_tag, calibration):
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    values = {"sheet_id": sheet.pk, "request_id": "r1", "duration_s": 420, "calibration_id": calibration.pk}
    failed = services.record_run(**values, outcome="failed")
    sheet.refresh_from_db()
    assert sheet.status == "planned"
    assert failed.material_cost == Decimal("45.00")
    assert failed.settings_snapshot["power_pct"] == 30

    assert services.record_run(**values, outcome="ok").pk == failed.pk  # الطلب نفسه لا يُسجَّل مرتين
    ok = services.record_run(**{**values, "request_id": "r2"}, outcome="ok")
    sheet.refresh_from_db()
    assert sheet.status == "done"
    assert RunLog.objects.count() == 2

    calibration.power_pct = 60
    calibration.save()
    ok.refresh_from_db()
    assert ok.settings_snapshot["power_pct"] == 30  # اللقطة لا تتبع تعديل المعايرة

    with pytest.raises(services.ProductionError):
        services.record_run(**{**values, "request_id": "r3"}, outcome="ok")  # اللوح أُغلق
    with pytest.raises(services.ProductionError):
        services.record_run(**{**values, "request_id": ""}, outcome="ok")


@pytest.mark.django_db
def test_record_run_rejects_calibration_of_another_material(material, name_tag, calibration):
    from datetime import date

    from apps.catalog import services as catalog_services

    other = catalog_services.upsert_material(name="خشب", kind="wood", thickness_mm=Decimal("3"))
    foreign = catalog_services.record_calibration(
        material=other,
        operation="cut",
        power_pct=80,
        speed_mm_s=Decimal("10"),
        min_line_mm=Decimal("0.2"),
        measured_on=date(2026, 11, 16),
    )
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    with pytest.raises(services.ProductionError):
        services.record_run(
            sheet_id=sheet.pk, request_id="r1", duration_s=1, outcome="ok", calibration_id=foreign.pk
        )
    assert not RunLog.objects.exists()


@pytest.mark.django_db
def test_production_api(client, staff_user, material, name_tag, calibration):
    assert client.get("/api/production/sheets").status_code == 401
    _confirmed_order(material, 2)
    client.force_login(staff_user)
    res = client.post(
        "/api/production/sheets/plan", {"material_id": material.pk}, content_type="application/json"
    )
    assert res.status_code == 200, res.content
    (sheet,) = res.json()
    assert len(sheet["placements"]) == 2
    assert (
        client.post(
            "/api/production/sheets/plan", {"material_id": 999999}, content_type="application/json"
        ).status_code
        == 404
    )

    url = f"/api/production/sheets/{sheet['id']}/runs"
    body = {"duration_s": 300, "outcome": "ok", "calibration_id": calibration.pk}
    assert client.post(url, body, content_type="application/json").status_code == 409  # بلا X-Request-ID
    assert client.post(url, {**body, "outcome": "meh"}, content_type="application/json").status_code == 422
    res = client.post(url, body, content_type="application/json", headers={"X-Request-ID": "run-1"})
    assert res.status_code == 200, res.content
    again = client.post(url, body, content_type="application/json", headers={"X-Request-ID": "run-1"})
    assert again.json()["id"] == res.json()["id"]
    assert client.get("/api/production/sheets?status=done").json()[0]["id"] == sheet["id"]


@pytest.mark.django_db
def test_cancelling_order_releases_its_planned_pieces(material, name_tag, calibration):
    from apps.core.models import AuditLog

    kept = _confirmed_order(material, 30)
    cancelled = _confirmed_order(material, 10)
    first, second = sorted(services.plan_sheets(material_id=material.pk), key=lambda sheet: sheet.pk)
    assert Placement.objects.filter(order_item__order=cancelled).count() == 10

    order_services.transition(order_id=cancelled.pk, to_status="cancelled")
    assert not Placement.objects.filter(order_item__order=cancelled).exists()
    assert Placement.objects.filter(order_item__order=kept).count() == 30
    # اللوح الثاني كان كله للطلب الملغى ولم يُشغَّل: يُحذف. الأول بقيت عليه قطع الطلب الآخر.
    assert list(Sheet.objects.values_list("pk", "status")) == [(first.pk, "planned")]
    audit = AuditLog.objects.get(action="production.release")
    assert audit.target == f"order:{cancelled.pk}"
    assert audit.payload == {
        "pieces": 10,
        "sheets": [first.pk, second.pk],
        "deleted": [second.pk],
        "scrapped": [],
    }

    assert services.release_order(order_id=cancelled.pk) == 0  # idempotent
    assert AuditLog.objects.filter(action="production.release").count() == 1
    assert services.plan_sheets(material_id=material.pk) == []  # الملغى لا يُعاد تخطيطه


@pytest.mark.django_db
def test_cancelling_keeps_cut_sheets_and_scraps_emptied_failed_ones(material, name_tag, calibration):
    order = _confirmed_order(material, 40)
    done, failed = sorted(services.plan_sheets(material_id=material.pk), key=lambda sheet: sheet.pk)
    services.record_run(sheet_id=done.pk, request_id="r1", duration_s=60, outcome="ok")
    services.record_run(sheet_id=failed.pk, request_id="r2", duration_s=60, outcome="failed")
    order_services.transition(order_id=order.pk, to_status="in_production")

    order_services.transition(order_id=order.pk, to_status="cancelled")
    # ما قُصّ يبقى سجله كما هو؛ اللوح الذي فشل تشغيله وفرغ لا يُحذف (سجل تشغيله محميّ) بل يُعلَّم تالفًا.
    assert Placement.objects.filter(sheet=done).count() == 35
    assert not Placement.objects.filter(sheet=failed).exists()
    assert dict(Sheet.objects.values_list("pk", "status")) == {done.pk: "done", failed.pk: "scrapped"}
    assert RunLog.objects.count() == 2


@pytest.mark.django_db
def test_cancel_rolls_back_when_release_fails(material, name_tag, calibration, monkeypatch):
    from apps.orders.models import Order

    order = _confirmed_order(material, 2)
    services.plan_sheets(material_id=material.pk)

    def boom(**kwargs):
        raise RuntimeError("تعذّر التحرير")

    monkeypatch.setattr(services, "release_order", boom)
    with pytest.raises(RuntimeError):
        order_services.transition(order_id=order.pk, to_status="cancelled")
    assert Order.objects.get(pk=order.pk).status == "confirmed"
    assert Placement.objects.count() == 2
