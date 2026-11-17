"""بوابة الدمج: ما يُدمج من الجلسة وما يبقى بيد المالك (المال، المسارات الحسّاسة، نافذة النشر)."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
sys.path.insert(0, str(ROOT / "scripts"))

import merge_gate  # noqa: E402

RULES = json.loads((ROOT / "security" / "sensitive_paths.json").read_text(encoding="utf-8"))
HEAD = "564d2a4b" + "0" * 32
APPROVED = "اعتُمد من المالك — 2026-11-17 — الرأس 564d2a4b"
GREEN = [{"name": "بوابة الجودة", "conclusion": "SUCCESS", "startedAt": "2026-11-17T16:00:00Z"}]
# خارج الدوام: الجمعة 20:00 بتوقيت الدوحة.
OFF_HOURS = datetime(2026, 11, 20, 17, 0, tzinfo=UTC)
# وقت الدوام: الأحد 10:00 بتوقيت الدوحة.
WORK_HOURS = datetime(2026, 11, 22, 7, 0, tzinfo=UTC)


def diff_of(path: str, *lines: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n" + "\n".join(lines) + "\n"


@pytest.fixture
def gate(monkeypatch):
    """بوابة معزولة عن gh والشبكة: الطلب وفرقه يُعطيان مباشرة."""

    def build(
        *, body=APPROVED, files=("frontend/src/pages/HomePage.vue",), diff="", checks=None, labels=(), **extra
    ):
        pr = {
            "body": body,
            "files": [{"path": p} for p in files],
            "statusCheckRollup": GREEN if checks is None else checks,
            "headRefOid": HEAD,
            "labels": [{"name": name} for name in labels],
            "state": "OPEN",
            "isDraft": False,
            **extra,
        }
        monkeypatch.setattr(merge_gate, "gh_json", lambda args: pr)
        monkeypatch.setattr(merge_gate, "load_rules", lambda: RULES)

        class Done:
            stdout = diff
            returncode = 0

        calls: list[list[str]] = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            return Done()

        monkeypatch.setattr(merge_gate.subprocess, "run", run)
        return calls

    return build


def test_clean_approved_green_pr_is_allowed(gate):
    gate(diff=diff_of("frontend/src/pages/HomePage.vue", "+.slogan { align-self: flex-start; }"))
    ok, reasons, head = merge_gate.evaluate("19", None)
    assert ok, reasons
    assert head == HEAD


@pytest.mark.parametrize(
    ("body", "expected"),
    [("", "لا سطر اعتماد"), ("اعتُمد من المالك — 2026-11-17 — الرأس c50df87f", "رأس قديم")],
)
def test_owner_approval_must_match_head(gate, body, expected):
    gate(body=body)
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert not ok
    assert any(expected in r for r in reasons)


@pytest.mark.parametrize(
    "path",
    [
        "apps/orders/migrations/0002_total.py",
        "config/settings/production.py",
        "apps/core/permissions.py",
        "apps/orders/payment_service.py",
        "frontend/src/pages/InvoicePage.vue",
        ".github/workflows/quality-gate.yml",
        "scripts/merge_gate.py",
        "security/sensitive_paths.json",
        ".claude/settings.json",
        "Dockerfile",
    ],
)
def test_sensitive_paths_stay_manual(gate, path):
    gate(files=(path,))
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert not ok
    assert any("مسارات محظورة" in r and path in r for r in reasons)


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("apps/orders/services.py", "+    order.total = sum(item.price for item in items)"),
        ("apps/catalog/models.py", "-    unit_price = models.DecimalField(max_digits=8, decimal_places=2)"),
        ("frontend/src/pages/OrderNewPage.vue", '+      <span class="muted">الإجمالي {{ sum }} ريال</span>'),
    ],
)
def test_money_changes_stay_manual(gate, path, line):
    gate(files=(path,), diff=diff_of(path, line))
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert not ok
    assert any("money" in r and path in r for r in reasons)


def test_money_words_outside_app_code_do_not_block(gate):
    path = "docs/pricing-notes.md"
    assert merge_gate.content_hits(diff_of(path, "+السعر يُراجع لاحقًا"), RULES) == []


def test_unchanged_context_lines_do_not_block(gate):
    path = "apps/orders/services.py"
    diff = diff_of(path, " total = compute(order)", "+    logger.info('saved')")
    assert merge_gate.content_hits(diff, RULES) == []


def test_only_latest_run_of_each_check_counts(gate):
    checks = [
        {"name": "approval-head", "conclusion": "FAILURE", "startedAt": "2026-11-17T16:02:00Z"},
        {"name": "approval-head", "conclusion": "SUCCESS", "startedAt": "2026-11-17T16:30:00Z"},
    ]
    gate(checks=checks)
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert ok, reasons


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ([], "لا فحوص"),
        ([{"name": "بوابة الجودة", "conclusion": "FAILURE"}], "فحص فاشل"),
        ([{"name": "بوابة الجودة", "state": "PENDING"}], "لم يكتمل"),
    ],
)
def test_checks_must_be_green(gate, checks, expected):
    gate(checks=checks)
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert not ok
    assert any(expected in r for r in reasons)


def test_closed_or_draft_pr_is_refused(gate):
    gate(state="MERGED")
    ok, reasons, _ = merge_gate.evaluate("19", None)
    assert not ok
    assert any("ليس مفتوحًا" in r for r in reasons)


def test_deploy_window_blocks_session_merge_unless_urgent():
    assert merge_gate.window_reason([], OFF_HOURS) is None
    assert "نافذة النشر" in (merge_gate.window_reason([], WORK_HOURS) or "")
    assert merge_gate.window_reason(["نشر-عاجل"], WORK_HOURS) is None


def test_merge_is_squash_pinned_to_approved_head(gate, monkeypatch):
    calls = gate()
    monkeypatch.setattr(merge_gate, "window_reason", lambda labels, now: None)
    monkeypatch.setattr(sys, "argv", ["merge_gate.py", "19", "--repo", "mesuef1974/misk", "--merge"])
    assert merge_gate.main() == 0
    assert calls[-1] == [
        "gh", "pr", "merge", "19", "--squash", "--match-head-commit", HEAD, "--repo", "mesuef1974/misk",
    ]  # fmt: skip


def test_refused_pr_is_never_merged(gate, monkeypatch):
    calls = gate(files=("apps/orders/migrations/0002_total.py",))
    monkeypatch.setattr(sys, "argv", ["merge_gate.py", "19", "--merge"])
    assert merge_gate.main() == 1
    assert not any(cmd[:3] == ["gh", "pr", "merge"] for cmd in calls)
