"""نافذة النشر: الحكم على الطلب وطابور الدمج، ومتى يُعاد الفحص المجدوَل."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deploy_window as dw  # noqa: E402

# 2026-11-18 أربعاء. الإزاحة +3: 06:00 UTC = 09:00 محليًا (دوام)، 12:00 UTC = 15:00 (بعده).
IN_WINDOW = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
AFTER_WINDOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
FRIDAY = datetime(2026, 11, 20, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (IN_WINDOW, True),
        (AFTER_WINDOW, False),
        (FRIDAY, False),
        (datetime(2026, 11, 18, 3, 59, tzinfo=UTC), False),  # 06:59
        (datetime(2026, 11, 18, 4, 0, tzinfo=UTC), True),  # 07:00
        (datetime(2026, 11, 18, 10, 59, tzinfo=UTC), True),  # 13:59
        (datetime(2026, 11, 18, 11, 0, tzinfo=UTC), False),  # 14:00
        (datetime(2026, 11, 21, 22, 0, tzinfo=UTC), False),  # الأحد 01:00 محليًا: يوم دوام خارج ساعاته
        (datetime(2026, 11, 22, 5, 0, tzinfo=UTC), True),  # الأحد 08:00
    ],
)
def test_in_work_hours(now, expected):
    assert dw.in_work_hours(now) is expected


@pytest.mark.parametrize("event", ["pull_request", "merge_group"])
def test_blocked_in_window_without_label(event):
    for labels in (None, [], ["bug"]):
        allowed, message = dw.decide(event, IN_WINDOW, labels)
        assert allowed is False
        assert dw.LABEL in message


@pytest.mark.parametrize("event", ["pull_request", "merge_group"])
def test_urgent_label_passes_in_window(event):
    assert dw.decide(event, IN_WINDOW, ["bug", dw.LABEL])[0] is True


@pytest.mark.parametrize("event", ["pull_request", "merge_group", "workflow_dispatch"])
def test_allowed_outside_window(event):
    assert dw.decide(event, AFTER_WINDOW, None)[0] is True
    assert dw.decide(event, FRIDAY, None)[0] is True


def test_unenforced_event_is_not_blocked_in_window():
    assert dw.decide("workflow_dispatch", IN_WINDOW, None)[0] is True


def test_pr_number_per_event():
    assert dw.pr_number("pull_request", {"PR_NUMBER": "28"}) == 28
    assert dw.pr_number("pull_request", {"PR_NUMBER": ""}) is None
    assert dw.pr_number("pull_request", {}) is None
    assert dw.pr_number("merge_group", {"HEAD_REF": "refs/heads/gh-readonly-queue/main/pr-17-abc"}) == 17
    assert dw.pr_number("merge_group", {"HEAD_REF": "refs/heads/main"}) is None


@pytest.mark.parametrize(
    ("conclusion", "allowed", "expected"),
    [
        ("success", False, True),  # أخضر قبل الدوام ثم بدأ الدوام
        ("failure", True, True),  # أحمر في الدوام ثم انتهى
        ("success", True, False),
        ("failure", False, False),
        (None, False, False),  # جارٍ: سيُحسب بوقته
        ("cancelled", True, False),
        ("skipped", False, False),
    ],
)
def test_needs_rerun(conclusion, allowed, expected):
    assert dw.needs_rerun(conclusion, allowed) is expected


def test_main_blocks_pull_request_in_window_and_reads_labels_live(monkeypatch, capsys):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return IN_WINDOW

    seen: list[tuple[str, int]] = []

    def fake_labels(repo, number):
        seen.append((repo, number))
        return []

    monkeypatch.setattr(dw, "datetime", Frozen)
    monkeypatch.setattr(dw, "pr_labels", fake_labels)
    monkeypatch.setenv("EVENT", "pull_request")
    monkeypatch.setenv("PR_NUMBER", "28")
    monkeypatch.setenv("REPO", "o/r")
    assert dw.main([]) == 1
    assert seen == [("o/r", 28)]
    assert "::error::" in capsys.readouterr().out

    monkeypatch.setattr(dw, "pr_labels", lambda repo, number: [dw.LABEL])
    assert dw.main([]) == 0


def test_main_fails_closed_without_pr_number(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return IN_WINDOW

    monkeypatch.setattr(dw, "datetime", Frozen)
    monkeypatch.setenv("EVENT", "pull_request")
    monkeypatch.delenv("PR_NUMBER", raising=False)
    assert dw.main([]) == 1


def test_refresh_reruns_only_changed_verdicts(monkeypatch, capsys):
    prs = [
        {"number": 1, "sha": "a", "labels": []},  # أخضر والآن دوام: يُعاد
        {"number": 2, "sha": "b", "labels": [dw.LABEL]},  # أخضر وموسوم: يبقى
        {"number": 3, "sha": "c", "labels": []},  # أحمر والآن دوام: يبقى
        {"number": 4, "sha": "d", "labels": []},  # لا تشغيل له: يُترك
    ]
    jobs = {
        "a": {"id": 11, "conclusion": "success"},
        "b": {"id": 12, "conclusion": "success"},
        "c": {"id": 13, "conclusion": "failure"},
        "d": None,
    }
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(dw, "_gh_json", lambda *a: prs)
    monkeypatch.setattr(dw, "window_job", lambda repo, sha: jobs[sha])
    monkeypatch.setattr(dw.subprocess, "run", fake_run)
    assert dw.refresh("o/r", IN_WINDOW) == 0
    assert [c[-1] for c in calls] == ["repos/o/r/actions/jobs/11/rerun"]

    calls.clear()
    assert dw.refresh("o/r", AFTER_WINDOW) == 0
    assert [c[-1] for c in calls] == ["repos/o/r/actions/jobs/13/rerun"]
    capsys.readouterr()


def test_refresh_reports_failed_rerun(monkeypatch, capsys):
    class Failed:
        returncode = 1
        stderr = "HTTP 403"

    monkeypatch.setattr(dw, "_gh_json", lambda *a: [{"number": 1, "sha": "a", "labels": []}])
    monkeypatch.setattr(dw, "window_job", lambda repo, sha: {"id": 11, "conclusion": "success"})
    monkeypatch.setattr(dw.subprocess, "run", lambda cmd, **kw: Failed())
    assert dw.refresh("o/r", IN_WINDOW) == 1
    assert "HTTP 403" in capsys.readouterr().out
