"""دفتر البطاقات ومسارات المشغّل التي لا يغطيها tests/test_gates.py (فجوة الاختبار في مراجعة 2026-11-19).

test_gates.py يغطي القفل، والمسارات المحظورة، وموانع الدفع، والأدوات المحجوبة. هنا: الدفتر كله،
وفروع المشغّل الباقية (لا بطاقة، والتجربة الجافة، وفشل الفحص، ومانع الدفع، والنجاح)، وأن القفل يُحرَّر في كلٍّ منها.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "automation"))

import ledger  # noqa: E402
import runner  # noqa: E402

HEAD = "7e3477d3" + "0" * 32


@pytest.fixture
def book(tmp_path, monkeypatch):
    """دفتر في مجلد مؤقت: لا يمسّ automation/ledger الحقيقي."""
    monkeypatch.setattr(ledger, "LEDGER", tmp_path / "ledger")
    return tmp_path / "ledger"


# الدفتر


def test_ledger_is_empty_before_any_card(book):
    assert ledger.all_cards() == []
    assert ledger.events("absent") == []
    assert ledger.state("absent") is None
    assert ledger.first("absent") is None


def test_ledger_rejects_an_unknown_event_and_writes_nothing(book):
    with pytest.raises(ValueError, match="حدث غير معروف"):
        ledger.append("c1", "shipped")
    assert not ledger.card_path("c1").exists()


def test_ledger_appends_only_and_state_is_the_last_event(book):
    ledger.append("c1", "created", title="عنوان")
    ledger.append("c1", "ready")
    ledger.append("c1", "blocked", reason="dirty_tree")
    lines = ledger.card_path("c1").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["created", "ready", "blocked"]
    assert ledger.state("c1")["reason"] == "dirty_tree"
    assert ledger.first("c1")["title"] == "عنوان"


def test_ledger_keeps_arabic_readable_and_skips_blank_lines(book):
    ledger.append("c1", "created", title="بطاقة عربية")
    with ledger.card_path("c1").open("a", encoding="utf-8") as fh:
        fh.write("\n   \n")
    assert "بطاقة عربية" in ledger.card_path("c1").read_text(encoding="utf-8")
    assert len(ledger.events("c1")) == 1


def test_ledger_cards_in_filters_by_current_state_only(book):
    for card, trail in {
        "b": ["created", "ready"],
        "a": ["created", "ready"],
        "c": ["ready", "claimed"],
    }.items():
        for event in trail:
            ledger.append(card, event)
    assert ledger.all_cards() == ["a", "b", "c"]
    assert ledger.cards_in("ready") == ["a", "b"]  # c كانت ready ثم التُقطت
    assert ledger.cards_in("claimed", "blocked") == ["c"]


def test_ledger_new_card_has_a_dated_id_and_a_created_event(book):
    card = ledger.new_card("عنوان", "المطلوب", success="اختبار ينجح")
    assert re.fullmatch(r"\d{8}-[0-9a-f]{6}", card)
    assert ledger.events(card) == [
        {
            "card": card,
            "event": "created",
            "at": ledger.first(card)["at"],
            "title": "عنوان",
            "body": "المطلوب",
            "success": "اختبار ينجح",
        }
    ]


def test_ledger_cli_walks_a_card_from_new_to_list(book, capsys):
    assert ledger.main(["new", "بطاقة", "--body", "افعل"]) == 0
    card = capsys.readouterr().out.strip()
    assert ledger.main(["ready", card]) == 0
    assert ledger.main(["event", card, "blocked", "--note", "ينتظر"]) == 0
    capsys.readouterr()
    assert ledger.main(["list"]) == 0
    assert capsys.readouterr().out.split() == [card, "blocked", "بطاقة"]
    assert ledger.main(["show", card]) == 0
    assert [json.loads(line)["event"] for line in capsys.readouterr().out.splitlines()] == [
        "created",
        "ready",
        "blocked",
    ]


def test_ledger_cli_refuses_an_unknown_event(book):
    with pytest.raises(SystemExit):
        ledger.main(["event", "c1", "shipped"])
    assert not ledger.card_path("c1").exists()


# المشغّل


@pytest.fixture
def run(book, tmp_path, monkeypatch):
    """مشغّل ببطاقة ready واحدة وكل ما يلمس git والنموذج والشبكة مستبدَل. يعيد (أحداث البطاقة، الاستدعاءات)."""
    monkeypatch.setattr(runner, "LOCK", tmp_path / ".lock")
    ledger.append("card1", "created", title="عنوان", body="المطلوب", success="ينجح")
    ledger.append("card1", "ready")
    calls: list[str] = []
    worktree = tmp_path / "wt"

    def record(name, value=None):
        def fake(*args, **kwargs):
            calls.append(name)
            return value

        return fake

    monkeypatch.setattr(runner, "make_worktree", record("worktree", (worktree, "card/card1")))
    monkeypatch.setattr(runner, "run_model", record("model", 0))
    monkeypatch.setattr(runner, "touched_forbidden", record("forbidden", []))
    monkeypatch.setattr(runner, "prepush", record("prepush", True))
    monkeypatch.setattr(runner, "unpushable", record("unpushable", None))
    monkeypatch.setattr(runner, "push_and_open_pr", record("push", "https://github.com/o/r/pull/9"))
    monkeypatch.setattr(runner, "sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, HEAD + "\n", ""))
    return (lambda: [e["event"] for e in ledger.events("card1")]), calls


def test_runner_without_ready_cards_takes_no_lock(book, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner, "LOCK", tmp_path / ".lock")
    ledger.append("done", "merged")
    assert runner.main([]) == 0
    assert "لا بطاقات ready" in capsys.readouterr().out
    assert not runner.LOCK.exists()


def test_runner_dry_run_changes_nothing(run, capsys):
    trail, calls = run
    assert runner.main(["--dry-run"]) == 0
    assert "card1" in capsys.readouterr().out
    assert trail() == ["created", "ready"] and calls == []
    assert not runner.LOCK.exists()


def test_runner_happy_path_records_each_step_and_opens_the_pr(run):
    trail, calls = run
    assert runner.main([]) == 0
    assert trail() == ["created", "ready", "claimed", "coded", "prepush_ok", "pr_opened"]
    assert calls == ["worktree", "model", "forbidden", "prepush", "unpushable", "push"]
    state = ledger.state("card1")
    assert (state["url"], state["head"]) == ("https://github.com/o/r/pull/9", HEAD)
    assert not runner.LOCK.exists()


def test_runner_failed_prepush_neither_pushes_nor_keeps_the_lock(run, monkeypatch):
    trail, calls = run
    monkeypatch.setattr(runner, "prepush", lambda path: False)
    assert runner.main([]) == 1
    assert trail()[-1] == "prepush_failed"
    assert "unpushable" not in calls and "push" not in calls
    assert not runner.LOCK.exists()


def test_runner_push_blocker_is_recorded_as_blocked_with_its_reason(run, monkeypatch):
    trail, calls = run
    monkeypatch.setattr(runner, "unpushable", lambda path, head: "head_moved")
    assert runner.main([]) == 1
    assert trail()[-2:] == ["prepush_ok", "blocked"]
    assert ledger.state("card1")["reason"] == "head_moved"
    assert "push" not in calls
    assert not runner.LOCK.exists()


def test_runner_releases_the_lock_when_a_step_raises(run, monkeypatch):
    def broken(*args, **kwargs):
        raise subprocess.CalledProcessError(128, ["git", "worktree", "add"])

    monkeypatch.setattr(runner, "make_worktree", broken)
    with pytest.raises(subprocess.CalledProcessError):
        runner.main([])
    assert not runner.LOCK.exists()


def test_runner_leaves_a_held_lock_alone(run, capsys):
    trail, calls = run
    runner.LOCK.write_text("other", encoding="utf-8")
    assert runner.main([]) == 0
    assert "مشغّل آخر يعمل" in capsys.readouterr().out
    assert trail() == ["created", "ready"] and calls == []
    assert runner.LOCK.read_text(encoding="utf-8") == "other"


def test_runner_starts_the_model_with_reduced_permissions(book, tmp_path, monkeypatch):
    ledger.append("card1", "created", title="عنوان", body="المطلوب", success="ينجح")
    seen = {}

    def fake_sh(cmd, cwd=None, check=True, **kw):
        seen.update(cmd=cmd, cwd=cwd)
        return subprocess.CompletedProcess(cmd, 7, "", "")

    monkeypatch.setattr(runner, "sh", fake_sh)
    assert runner.run_model(tmp_path, "card1", "claude-test", 12) == 7
    cmd = seen["cmd"]
    assert seen["cwd"] == tmp_path
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd[cmd.index("--max-turns") + 1] == "12"
    assert cmd[cmd.index("--model") + 1] == "claude-test"
    denied = cmd[cmd.index("--disallowedTools") + 1 : cmd.index("--model")]
    assert denied == runner.DISALLOWED_TOOLS
    prompt = cmd[cmd.index("-p") + 1]
    assert all(part in prompt for part in ("عنوان", "المطلوب", "ينجح", "لا تدفع"))


def test_runner_pr_body_asks_for_the_owner_line_and_does_not_write_it(book, tmp_path, monkeypatch):
    ledger.append("card1", "created", title="عنوان", body="المطلوب", success="ينجح")
    commands = []

    def fake_sh(cmd, cwd=None, check=True, **kw):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "https://github.com/o/r/pull/9\n", "")

    monkeypatch.setattr(runner, "sh", fake_sh)
    assert runner.push_and_open_pr(tmp_path, "card/card1", "card1") == "https://github.com/o/r/pull/9"
    push, create = commands
    assert push == ["git", "push", "-u", "origin", "card/card1"]
    body = create[create.index("--body") + 1]
    assert create[create.index("--title") + 1] == "عنوان"
    assert "card1" in body and "المطلوب" in body
    # السطر قالب بلا SHA حقيقي: فحص approval-head لا يقبله، فلا يُعتمد الطلب بلا مراجعة المالك.
    assert not re.search(r"الرأس [0-9a-f]{7,}", body)
