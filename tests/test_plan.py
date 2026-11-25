"""خطة النمو: صلاحية الملف الحقيقي، وحالة الخطوة من الدفتر، وحالة المؤشر، واكتشاف التقرير القديم."""

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
sys.path.insert(0, str(ROOT / "automation"))

import ledger  # noqa: E402
import plan as growth  # noqa: E402

TODAY = date(2026, 12, 1)


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "ledger")
    monkeypatch.setattr(growth, "PLAN", tmp_path / "plan.json")
    monkeypatch.setattr(growth, "REPORT", tmp_path / "plan.md")
    monkeypatch.setattr(growth, "ROOT", tmp_path)
    return tmp_path


def sample() -> dict:
    return {
        "title": "خطة",
        "review": "أسبوعيًّا",
        "phases": [{"id": "P0", "title": "أساس", "from": "2026-11-30", "to": "2026-12-13"}],
        "initiatives": [
            {
                "id": "A",
                "title": "مبادرة",
                "phase": "P0",
                "why": "سبب",
                "steps": [{"id": "A.1", "title": "خطوة", "status": "pending", "card": None}],
                "kpis": [
                    {
                        "id": "A.k1",
                        "name": "مؤشر",
                        "unit": "٪",
                        "direction": "up",
                        "baseline": 0,
                        "target": 50,
                        "due": "2026-12-13",
                        "source": "db",
                        "value": None,
                        "measured_at": None,
                    }
                ],
            }
        ],
    }


def test_real_plan_is_valid_and_report_is_current():
    """الملف المودَع صالح وتقريره مولَّد منه: من عدّل الخطة ونسي `render` يفشل هنا."""
    assert not growth.is_stale(growth.load())


def test_step_status_follows_the_ledger(book):
    plan = sample()
    step = plan["initiatives"][0]["steps"][0]
    assert growth.step_status(step) == "pending"
    step["card"] = ledger.new_card("بطاقة", "وصف")
    assert growth.step_status(step) == "pending"
    ledger.append(step["card"], "claimed")
    assert growth.step_status(step) == "in_progress"
    ledger.append(step["card"], "merged")
    assert growth.step_status(step) == "done"


def test_kpi_status_from_value_target_and_due():
    kpi = sample()["initiatives"][0]["kpis"][0]
    assert growth.kpi_status(kpi, TODAY) == "لم يُقَس"
    kpi["value"] = 20
    assert growth.kpi_status(kpi, TODAY) == "جارٍ"
    assert growth.kpi_status(kpi, date(2026, 12, 14)) == "متأخر"
    kpi["value"] = 50
    assert growth.kpi_status(kpi, date(2026, 12, 14)) == "تحقق"
    kpi.update(direction="down", target=10, value=12)
    assert growth.kpi_status(kpi, TODAY) == "جارٍ"
    kpi["target"] = None
    assert growth.kpi_status(kpi, TODAY) == "ينتظر خط الأساس"


def test_ingest_records_values_and_rejects_unknown_ids():
    plan = sample()
    assert growth.ingest(plan, {"A.k1": 35}, TODAY) == ["A.k1"]
    kpi = plan["initiatives"][0]["kpis"][0]
    assert (kpi["value"], kpi["measured_at"]) == (35, "2026-12-01")
    with pytest.raises(growth.PlanError):
        growth.ingest(plan, {"غير موجود": 1}, TODAY)


def test_ingest_takes_the_date_of_a_saved_snapshot():
    plan = sample()
    saved = {"week_end": "2026-11-28", "metrics": {"A.k1": 12}}
    assert growth.ingest(plan, saved, TODAY) == ["A.k1"]
    kpi = plan["initiatives"][0]["kpis"][0]
    assert (kpi["value"], kpi["measured_at"]) == (12, "2026-11-28")
    with pytest.raises(growth.PlanError):
        growth.ingest(plan, {"week_end": "الأحد", "metrics": {"A.k1": 1}}, TODAY)


def test_validate_rejects_broken_plans():
    for path, value in (("phase", "P9"), ("depends_on", ["Z"])):
        plan = sample()
        plan["initiatives"][0][path] = value
        with pytest.raises(growth.PlanError):
            growth.validate(plan)
    plan = sample()
    plan["initiatives"][0]["steps"].append(copy.deepcopy(plan["initiatives"][0]["steps"][0]))
    with pytest.raises(growth.PlanError):
        growth.validate(plan)


def test_cli_renders_and_detects_stale_report(book, capsys):
    (book / "plan.json").write_text(json.dumps(sample(), ensure_ascii=False), encoding="utf-8")
    assert growth.main(["check"]) == 1
    assert growth.main(["--date", "2026-12-01", "render"]) == 0
    assert growth.main(["check"]) == 0
    assert growth.main(["--date", "2026-12-01", "kpi", "A.k1", "60"]) == 0
    report = (book / "plan.md").read_text(encoding="utf-8")
    assert "| 60 |" in report and "تحقق" in report
    assert growth.main(["check"]) == 0
    capsys.readouterr()
