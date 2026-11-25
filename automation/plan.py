#!/usr/bin/env python3
"""خطة النمو: `docs/growth-plan.json` مصدر الحقيقة، و`docs/growth-plan.md` تقرير مولَّد منه لا يُحرَّر يدويًّا.

حالة الخطوة المربوطة ببطاقة تُقرأ من دفتر البطاقات، فتتحدّث بلا تدخل. قيم المؤشرات تدخل بـ`kpi` أو `ingest`
(لقطة JSON يخرجها أمر القياس)، وحالتها تُحسب من القيمة والهدف والموعد.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path

import ledger

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "growth-plan.json"
REPORT = ROOT / "docs" / "growth-plan.md"
STEP_STATES = ("pending", "in_progress", "done", "blocked")
STEP_LABELS = {"pending": "لم تبدأ", "in_progress": "جارية", "done": "تمت", "blocked": "محجوبة"}
DONE_EVENTS = ("merged", "deployed")
MARK = "<!-- plan-hash: "


class PlanError(ValueError):
    pass


def load(path: Path | None = None) -> dict:
    plan = json.loads((path or PLAN).read_text(encoding="utf-8"))
    validate(plan)
    return plan


def save(plan: dict, path: Path | None = None) -> None:
    validate(plan)
    (path or PLAN).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(plan: dict) -> None:
    phases = {p["id"] for p in plan["phases"]}
    ids = [i["id"] for i in plan["initiatives"]]
    seen: set[str] = set()
    for item in plan["initiatives"]:
        if item["phase"] not in phases:
            raise PlanError(f"{item['id']}: مرحلة غير معروفة {item['phase']}")
        for dep in item.get("depends_on", []):
            if dep not in ids:
                raise PlanError(f"{item['id']}: يعتمد على مبادرة غير موجودة {dep}")
        for step in item["steps"]:
            if step["status"] not in STEP_STATES:
                raise PlanError(f"{step['id']}: حالة غير معروفة {step['status']}")
        for row in [*item["steps"], *item["kpis"]]:
            if row["id"] in seen:
                raise PlanError(f"معرّف مكرر: {row['id']}")
            seen.add(row["id"])
        for kpi in item["kpis"]:
            if kpi["direction"] not in ("up", "down"):
                raise PlanError(f"{kpi['id']}: اتجاه غير معروف")
            date.fromisoformat(kpi["due"])


def step_status(step: dict) -> str:
    """البطاقة تغلب الحالة المكتوبة: الدفتر هو ما حدث فعلًا."""
    current = ledger.state(step["card"]) if step.get("card") else None
    if current is None:
        return step["status"]
    if current["event"] in DONE_EVENTS:
        return "done"
    if current["event"] in ("blocked", "prepush_failed"):
        return "blocked"
    return "pending" if current["event"] in ("created", "cancelled") else "in_progress"


def kpi_status(kpi: dict, today: date) -> str:
    if kpi["target"] is None:
        return "ينتظر خط الأساس"
    if kpi["value"] is None:
        return "لم يُقَس"
    met = kpi["value"] >= kpi["target"] if kpi["direction"] == "up" else kpi["value"] <= kpi["target"]
    if met:
        return "تحقق"
    return "متأخر" if today > date.fromisoformat(kpi["due"]) else "جارٍ"


def find_kpi(plan: dict, kpi_id: str) -> dict:
    for item in plan["initiatives"]:
        for kpi in item["kpis"]:
            if kpi["id"] == kpi_id:
                return kpi
    raise PlanError(f"مؤشر غير موجود: {kpi_id}")


def set_kpi(plan: dict, kpi_id: str, value: float, on: date, field: str = "value") -> None:
    kpi = find_kpi(plan, kpi_id)
    kpi[field] = value
    if field == "value":
        kpi["measured_at"] = on.isoformat()


def ingest(plan: dict, snapshot: dict, on: date) -> list[str]:
    """لقطة `{معرّف المؤشر: قيمة}`. المعرّف المجهول خطأ لا تجاهل: لقطة لا تطابق الخطة عيب يجب أن يظهر."""
    for kpi_id, value in snapshot.items():
        set_kpi(plan, kpi_id, value, on)
    return sorted(snapshot)


def _fingerprint(plan: dict) -> str:
    states = [step_status(s) for item in plan["initiatives"] for s in item["steps"]]
    raw = json.dumps([plan, states], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _num(value) -> str:
    return "—" if value is None else f"{value:g}"


def render(plan: dict, today: date) -> str:
    steps = [(item, s, step_status(s)) for item in plan["initiatives"] for s in item["steps"]]
    kpis = [(item, k, kpi_status(k, today)) for item in plan["initiatives"] for k in item["kpis"]]
    done = sum(1 for _, _, state in steps if state == "done")
    measured = sum(1 for _, k, _ in kpis if k["value"] is not None)
    out = [
        f"# {plan['title']}",
        "",
        "مولَّد من `docs/growth-plan.json` بـ`python automation/plan.py render`. لا يُحرَّر يدويًّا.",
        "",
        f"- آخر توليد: {today.isoformat()}",
        f"- الخطوات: {done} من {len(steps)} تمت",
        f"- المؤشرات: {measured} من {len(kpis)} مقيسة، "
        f"{sum(1 for *_, s in kpis if s == 'تحقق')} تحققت، {sum(1 for *_, s in kpis if s == 'متأخر')} متأخرة",
        f"- المراجعة: {plan['review']}",
        "",
        "## يحتاج المالك",
        "",
    ]
    blocked = [(item, s) for item, s, state in steps if state == "blocked"]
    out += [f"- {s['id']} ({item['title']}): {s.get('blocked_by') or s['title']}" for item, s in blocked] or [
        "لا شيء."
    ]
    for phase in plan["phases"]:
        out += ["", f"## {phase['id']}: {phase['title']} ({phase['from']} ← {phase['to']})"]
        for item in (i for i in plan["initiatives"] if i["phase"] == phase["id"]):
            deps = "، ".join(item.get("depends_on", [])) or "—"
            out += ["", f"### {item['id']}: {item['title']}", "", item["why"], "", f"يعتمد على: {deps}", ""]
            out += ["| الخطوة | الحالة | البطاقة |", "|---|---|---|"]
            out += [
                f"| {s['id']} {s['title']} | {STEP_LABELS[step_status(s)]} | {s.get('card') or '—'} |"
                for s in item["steps"]
            ]
            out += [
                "",
                "| المؤشر | الأساس | الهدف | القيمة | الموعد | الحالة | المصدر |",
                "|---|---|---|---|---|---|---|",
            ]
            for k in item["kpis"]:
                target = _num(k["target"]) if k["target"] is not None else k.get("target_rule", "—")
                out.append(
                    f"| {k['id']} {k['name']} ({k['unit']}) | {_num(k['baseline'])} | {target} | {_num(k['value'])} "
                    f"| {k['due']} | {kpi_status(k, today)} | {k['source']} |"
                )
    out += ["", f"{MARK}{_fingerprint(plan)} -->", ""]
    return "\n".join(out)


def is_stale(plan: dict) -> bool:
    """التقرير قديم إن تغيّرت الخطة أو حالة بطاقة بعد توليده."""
    if not REPORT.exists():
        return True
    return f"{MARK}{_fingerprint(plan)} -->" not in REPORT.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--date", type=date.fromisoformat, default=None, help="تاريخ القياس أو التوليد (افتراضه اليوم)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render", help="يولّد التقرير")
    sub.add_parser("check", help="يفشل إن كان التقرير قديمًا أو الخطة غير صالحة")
    p_kpi = sub.add_parser("kpi", help="يسجّل قيمة مؤشر")
    p_kpi.add_argument("id")
    p_kpi.add_argument("value", type=float)
    p_kpi.add_argument("--field", choices=("value", "baseline", "target"), default="value")
    p_in = sub.add_parser("ingest", help="يقرأ لقطة مؤشرات JSON")
    p_in.add_argument("file", type=Path)
    args = ap.parse_args(argv)
    today = args.date or date.today()  # noqa: DTZ011 — تاريخ تقويمي للمالك لا لحظة زمنية

    try:
        plan = load()
        if args.cmd == "check":
            if is_stale(plan):
                print("التقرير قديم: شغّل python automation/plan.py render")
                return 1
            print("الخطة صالحة والتقرير مطابق")
            return 0
        if args.cmd == "kpi":
            set_kpi(plan, args.id, args.value, today, args.field)
            save(plan)
        elif args.cmd == "ingest":
            names = ingest(plan, json.loads(args.file.read_text(encoding="utf-8")), today)
            save(plan)
            print(f"حُدِّث {len(names)} مؤشر")
    except (PlanError, KeyError, json.JSONDecodeError) as exc:
        print(f"خطأ في الخطة: {exc}")
        return 2
    REPORT.write_text(render(plan, today), encoding="utf-8")
    print(f"وُلِّد {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
