import uuid
from decimal import Decimal
from unittest.mock import ANY

import pytest

from apps.core.models import AuditLog
from apps.orders import services as order_services
from apps.production import domain, jobs, services, tasks
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
    outcome = tasks.plan_sheets_async.delay(material_id=material.pk).get()
    assert outcome == {"sheets": list(Sheet.objects.values_list("pk", flat=True))}


@pytest.mark.django_db
def test_redelivered_plan_task_returns_the_sheets_it_already_planned(material, name_tag, calibration):
    """acks_late: مهمة ثبّتت ألواحها ثم أُعيد تسليمها بالمعرّف نفسه لا تُبلغ بأن «لا ألواح»."""
    _confirmed_order(material, 2)
    task_id = str(uuid.uuid4())
    first = tasks.plan_sheets_async.apply(kwargs={"material_id": material.pk}, task_id=task_id).get()
    again = tasks.plan_sheets_async.apply(kwargs={"material_id": material.pk}, task_id=task_id).get()
    assert first == again == {"sheets": list(Sheet.objects.values_list("pk", flat=True))}
    assert first["sheets"]
    assert Sheet.objects.count() == 1 and AuditLog.objects.filter(action="production.plan").count() == 1
    # مهمة أخرى (نقرة ثانية) لم تنشئ شيئًا: تبقى قائمتها فارغة كي لا تُحسب ألواح غيرها جديدة.
    other = tasks.plan_sheets_async.apply(kwargs={"material_id": material.pk}, task_id=str(uuid.uuid4()))
    assert other.get() == {"sheets": []}


@pytest.mark.django_db
def test_plan_task_returns_business_error_without_retrying(material, name_tag, calibration):
    name_tag.width_mm = Decimal("700")
    name_tag.save()
    _confirmed_order(material, 1)
    assert tasks.plan_sheets_async.delay(material_id=material.pk).get() == {"error": ANY}
    assert not Sheet.objects.exists()


def _plan(client, material_id):
    return client.post(
        "/api/production/sheets/plan", {"material_id": material_id}, content_type="application/json"
    )


@pytest.mark.django_db
def test_plan_api_async_returns_job_and_polls_it(
    client, staff_user, material, name_tag, calibration, settings
):
    settings.PLANNING_ASYNC = True
    _confirmed_order(material, 2)
    client.force_login(staff_user)
    # التنفيذ الفوري في الاختبار يُنهي المهمة قبل الرد؛ المهم أن الرد يحمل معرّفًا يُستطلع بالشكل نفسه.
    started = _plan(client, material.pk)
    assert started.status_code == 200, started.content
    job = started.json()
    assert job["status"] == "done" and job["id"]
    (sheet,) = job["sheets"]
    assert len(sheet["placements"]) == 2
    polled = client.get(f"/api/production/sheets/plan/{job['id']}").json()
    assert (polled["status"], [s["id"] for s in polled["sheets"]]) == ("done", [sheet["id"]])
    assert AuditLog.objects.get(action="production.plan").actor == staff_user  # الفاعل يعبر إلى العامل

    assert _plan(client, 999999).status_code == 404  # المادة تُفحص قبل الطابور
    assert client.get("/api/production/sheets/plan/not-a-uuid").status_code == 404
    unknown = client.get(f"/api/production/sheets/plan/{uuid.uuid4()}").json()
    assert (unknown["status"], unknown["sheets"]) == ("pending", [])


@pytest.mark.django_db
def test_plan_api_async_reports_business_error_as_failed_job(
    client, staff_user, material, name_tag, calibration, settings
):
    settings.PLANNING_ASYNC = True
    name_tag.width_mm = Decimal("700")
    name_tag.save()
    _confirmed_order(material, 1)
    client.force_login(staff_user)
    job = _plan(client, material.pk).json()
    assert job["status"] == "failed" and job["error"]
    assert client.get(f"/api/production/sheets/plan/{job['id']}").json()["error"] == job["error"]


def test_plan_job_pending_while_worker_has_not_answered(monkeypatch):
    class Waiting:
        name = None  # Celery لا يحفظ الاسم بلا result_extended
        state = "PENDING"

    monkeypatch.setattr(jobs, "AsyncResult", lambda *args, **kwargs: Waiting())
    job_id = str(uuid.uuid4())
    assert jobs.plan_job(job_id) == jobs.PlanJob(id=job_id, status=jobs.PENDING)
    Waiting.state = "FAILURE"
    assert jobs.plan_job(job_id).error == jobs.WORKER_FAILED


@pytest.mark.parametrize(
    ("name", "outcome"),
    [
        (None, "نص"),
        (None, None),
        (None, ["sheets"]),
        (None, {"sheets": ["1"]}),
        (None, {"sheets": "1"}),
        (None, {"error": {"x": 1}}),
        ("apps.core.tasks.other", {"sheets": [1]}),
    ],
)
def test_plan_job_ignores_results_of_other_tasks(monkeypatch, name, outcome):
    """المعرّف يكتبه العميل: نتيجة مهمة أخرى «غير معروفة» لا 500 ولا ألواح."""

    class Other:
        state = "SUCCESS"

    Other.name, Other.result = name, outcome
    monkeypatch.setattr(jobs, "AsyncResult", lambda *args, **kwargs: Other())
    assert jobs.plan_job(str(uuid.uuid4())) is None


def test_plan_job_reads_a_plan_result(monkeypatch):
    class Done:
        name, state, result = tasks.plan_sheets_async.name, "SUCCESS", {"sheets": [3, 4]}

    monkeypatch.setattr(jobs, "AsyncResult", lambda *args, **kwargs: Done())
    assert jobs.plan_job(str(uuid.uuid4())).sheet_ids == [3, 4]


@pytest.mark.django_db
def test_plan_status_api_answers_404_for_foreign_result(client, staff_user, monkeypatch):
    class Other:
        name, state, result = None, "SUCCESS", "نص"

    monkeypatch.setattr(jobs, "AsyncResult", lambda *args, **kwargs: Other())
    client.force_login(staff_user)
    assert client.get(f"/api/production/sheets/plan/{uuid.uuid4()}").status_code == 404


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
    res = _plan(client, material.pk)
    assert res.status_code == 200, res.content
    assert (res.json()["status"], res.json()["id"]) == ("done", "")  # متزامن افتراضًا: لا شيء يُستطلع
    (sheet,) = res.json()["sheets"]
    assert len(sheet["placements"]) == 2
    assert _plan(client, 999999).status_code == 404

    url = f"/api/production/sheets/{sheet['id']}/runs"
    body = {"duration_s": 300, "outcome": "ok", "calibration_id": calibration.pk}
    assert client.post(url, body, content_type="application/json").status_code == 409  # بلا X-Request-ID
    assert client.post(url, {**body, "outcome": "meh"}, content_type="application/json").status_code == 422
    res = client.post(url, body, content_type="application/json", headers={"X-Request-ID": "run-1"})
    assert res.status_code == 200, res.content
    again = client.post(url, body, content_type="application/json", headers={"X-Request-ID": "run-1"})
    assert again.json()["id"] == res.json()["id"]
    done = client.get("/api/production/sheets?status=done").json()
    assert (done["count"], done["counts"]) == (1, {"done": 1})
    (listed,) = done["items"]
    assert listed["id"] == sheet["id"]
    assert [(run["id"], run["outcome"]) for run in listed["runs"]] == [(res.json()["id"], "ok")]
    piece = listed["placements"][0]
    assert (piece["customer_name"], piece["template_slug"]) == ("زبون تجريبي", "name-tag")
    assert client.get(f"/api/orders/{piece['order_id']}").json()["status"] == "in_production"
    assert client.get("/api/production/sheets?limit=0").status_code == 422


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


@pytest.mark.django_db
def test_record_run_rejects_bad_input_with_domain_error(material, name_tag, calibration):
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    for bad in (
        {"request_id": "r" * 65},
        {"duration_s": -1},
        {"duration_s": services.MAX_DURATION_S + 1},
        {"outcome": "meh"},
    ):
        values = {"sheet_id": sheet.pk, "request_id": "r1", "duration_s": 1, "outcome": "ok", **bad}
        with pytest.raises(services.ProductionError):
            services.record_run(**values)
    assert not RunLog.objects.exists()
    sheet.refresh_from_db()
    assert sheet.status == "planned"


@pytest.mark.django_db
def test_record_run_request_id_is_bound_to_its_sheet(material, name_tag, calibration):
    _confirmed_order(material, 40)
    first, second = services.plan_sheets(material_id=material.pk)
    services.record_run(sheet_id=first.pk, request_id="r1", duration_s=1, outcome="ok")
    with pytest.raises(services.ProductionError, match="request_id"):
        services.record_run(sheet_id=second.pk, request_id="r1", duration_s=1, outcome="ok")
    second.refresh_from_db()
    assert second.status == "planned"
    assert RunLog.objects.count() == 1


@pytest.mark.django_db
def test_record_run_survives_concurrent_duplicate(material, name_tag, calibration, monkeypatch):
    """سجل بالمفتاح نفسه أُدرج بعد فحصَي الوجود: قيد التفرّد يرفض والخدمة تعيد الموجود بلا 500."""
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    values = {"sheet_id": sheet.pk, "request_id": "r1", "duration_s": 5, "outcome": "failed"}
    winner = services.record_run(**values)
    real, calls = services._existing_run, []

    def racing(request_id, sheet_id):
        calls.append(request_id)
        return None if len(calls) <= 2 else real(request_id, sheet_id)

    monkeypatch.setattr(services, "_existing_run", racing)
    assert services.record_run(**values).pk == winner.pk
    assert len(calls) == 3
    assert RunLog.objects.count() == 1


@pytest.mark.django_db
def test_runs_api_rejects_bad_input_with_422(client, staff_user, material, name_tag, calibration):
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    client.force_login(staff_user)
    url = f"/api/production/sheets/{sheet.pk}/runs"

    def post(body, request_id="run-1"):
        return client.post(
            url, body, content_type="application/json", headers={"X-Request-ID": request_id}
        ).status_code

    ok = {"duration_s": 300, "outcome": "failed"}
    assert post(ok, request_id="r" * 65) == 422
    assert post({**ok, "duration_s": -1}) == 422
    assert post({**ok, "duration_s": 10**12}) == 422
    assert post({**ok, "notes": "م" * 2001}) == 422
    assert not RunLog.objects.exists()
    assert post(ok, request_id="r" * 64) == 200


@pytest.mark.django_db
def test_first_run_moves_confirmed_orders_into_production(material, name_tag, calibration):
    """أي تشغيل، ولو فشل، يبدأ العمل على طلبات اللوح. «جاهز» لا يُضبط آليًّا."""
    from apps.core.models import AuditLog

    order = _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    services.record_run(sheet_id=sheet.pk, request_id="r1", duration_s=60, outcome="failed")
    order.refresh_from_db()
    assert order.status == "in_production"
    services.record_run(sheet_id=sheet.pk, request_id="r2", duration_s=60, outcome="ok")
    order.refresh_from_db()
    assert order.status == "in_production"
    assert AuditLog.objects.filter(action="orders.transition", target=f"order:{order.pk}").count() == 2


@pytest.mark.django_db
def test_scrap_sheet_frees_pieces_for_replanning(material, name_tag, calibration):
    from apps.core.models import AuditLog

    _confirmed_order(material, 3)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    services.record_run(sheet_id=sheet.pk, request_id="r1", duration_s=60, outcome="failed")
    scrapped = services.scrap_sheet(sheet_id=sheet.pk)
    assert scrapped.status == "scrapped"
    assert not Placement.objects.filter(sheet=sheet).exists()
    assert RunLog.objects.filter(sheet=sheet).count() == 1  # سجل التشغيل الفاشل يبقى
    assert services.scrap_sheet(sheet_id=sheet.pk).status == "scrapped"  # idempotent
    assert AuditLog.objects.filter(action="production.scrap").count() == 1

    (again,) = services.plan_sheets(material_id=material.pk)  # القطع عادت تنتظر لوحًا
    assert again.pk != sheet.pk and again.placements.count() == 3
    with pytest.raises(services.ProductionError):
        services.record_run(sheet_id=sheet.pk, request_id="r2", duration_s=60, outcome="ok")


@pytest.mark.django_db
def test_scrap_api_refuses_done_sheet(client, staff_user, material, name_tag, calibration):
    _confirmed_order(material, 1)
    (sheet,) = services.plan_sheets(material_id=material.pk)
    url = f"/api/production/sheets/{sheet.pk}/scrap"
    assert client.post(url).status_code == 401
    client.force_login(staff_user)
    assert client.post("/api/production/sheets/999999/scrap").status_code == 404
    services.record_run(sheet_id=sheet.pk, request_id="r1", duration_s=60, outcome="ok")
    assert client.post(url).status_code == 409
    _confirmed_order(material, 1)
    (second,) = services.plan_sheets(material_id=material.pk)
    res = client.post(f"/api/production/sheets/{second.pk}/scrap")
    assert res.status_code == 200, res.content
    assert (res.json()["status"], res.json()["placements"]) == ("scrapped", [])


@pytest.mark.django_db
def test_sheet_list_query_count_is_constant(material, name_tag, calibration, django_assert_max_num_queries):
    from apps.production import selectors

    for _ in range(4):
        _confirmed_order(material, 2)
        services.plan_sheets(material_id=material.pk)
    with django_assert_max_num_queries(8):
        for sheet in selectors.sheets():
            assert [p.order_item.order.customer.name for p in sheet.placements.all()]
            assert [p.order_item.template.slug for p in sheet.placements.all()]
            assert list(sheet.runs.all()) == []


@pytest.mark.django_db
def test_plan_sheets_locks_orders_before_items(material, name_tag, calibration, monkeypatch):
    """الإلغاء يقفل الطلب ثم ألواحه؛ لو قفل التخطيط البنود وحدها لثبّت قطع طلب أُلغي أثناءه.
    SQLite يتجاهل FOR UPDATE، فالاختبار يثبت ترتيب الأقفال لا السباق نفسه (يحتاج PostgreSQL)."""
    from django.db.models import QuerySet

    planned = _confirmed_order(material, 3)
    locked = []
    real = QuerySet.select_for_update

    def spy(self, *args, **kwargs):
        locked.append(self.model._meta.label)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", spy)
    services.plan_sheets(material_id=material.pk)
    assert locked[:2] == ["orders.Order", "orders.OrderItem"]
    assert Placement.objects.filter(order_item__order=planned).count() == 3
