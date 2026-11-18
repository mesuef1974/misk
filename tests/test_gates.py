"""البوابات والمشغّل تفشل مغلقة: ما لم يُقَس لا يمرّ (docs/review-2026-11-16.md، القسم د)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "automation"))

import check_migration_collisions as collisions  # noqa: E402
import merge_gate  # noqa: E402
import prepush_check  # noqa: E402
import runner  # noqa: E402

HEAD = "564d2a4b" + "0" * 32
APPROVED = "اعتُمد من المالك — 2026-11-18 — الرأس 564d2a4b"
GREEN = [{"name": "بوابة الجودة", "conclusion": "SUCCESS"}]


def done(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


# ---------- بوابة الدمج


@pytest.fixture
def gate(monkeypatch):
    """بوابة معزولة عن gh: الطلب وملفاته يُعطيان مباشرة."""

    def build(*, body=APPROVED, files=({"filename": "frontend/src/pages/HomePage.vue"},), checks=None):
        pr = {"body": body, "headRefOid": HEAD, "statusCheckRollup": GREEN if checks is None else checks}
        monkeypatch.setattr(merge_gate, "gh_json", lambda args: [list(files)] if args[0] == "api" else pr)
        return merge_gate.evaluate("7", "owner/repo")

    return build


def test_gate_allows_approved_green_ordinary_change(gate):
    assert gate() == (True, [], HEAD)


@pytest.mark.parametrize("state", ["STALE", "STARTUP_FAILURE", "FAILURE", "CANCELLED", "SOMETHING_NEW"])
def test_gate_blocks_any_state_it_does_not_know_as_passing(gate, state):
    ok, reasons, _ = gate(checks=[*GREEN, {"name": "scan", "conclusion": state}])
    assert not ok
    assert any("scan" in reason for reason in reasons)


def test_gate_blocks_pending_and_missing_checks(gate):
    assert not gate(checks=[{"name": "scan", "state": "PENDING"}])[0]
    assert not gate(checks=[{"name": "scan"}])[0]
    assert not gate(checks=[])[0]


def test_gate_sees_the_old_name_of_a_renamed_sensitive_file(gate):
    renamed = {"filename": "apps/orders/notes.py", "previous_filename": "apps/orders/migrations/0002_x.py"}
    ok, reasons, _ = gate(files=(renamed,))
    assert not ok
    assert "apps/orders/migrations/0002_x.py" in reasons[0]


@pytest.mark.parametrize(
    "path",
    [
        "automation/runner.py",
        "pyproject.toml",
        "scripts/railway-release.sh",
        "scripts/check_migration_collisions.py",
        ".dockerignore",
        ".github/workflows/quality-gate.yml",
    ],
)
def test_gate_forbids_its_own_guards(gate, path):
    assert not gate(files=({"filename": path},))[0]


def test_gate_blocks_when_no_files_can_be_read(gate):
    assert not gate(files=())[0]


def test_gate_blocks_without_approval_or_on_a_stale_head(gate):
    assert not gate(body="")[0]
    assert not gate(body="اعتُمد من المالك — 2026-11-18 — الرأس aaaaaaaa")[0]


@pytest.mark.parametrize("content", [None, "{", "{}", '{"forbidden_for_auto_merge": []}'])
def test_gate_stops_when_the_rules_file_is_missing_or_broken(tmp_path, monkeypatch, content):
    rules = tmp_path / "sensitive_paths.json"
    if content is not None:
        rules.write_text(content, encoding="utf-8")
    monkeypatch.setattr(merge_gate, "RULES", rules)
    with pytest.raises(merge_gate.GateError):
        merge_gate.forbidden_globs()


def test_gate_main_reports_an_error_not_a_pass_when_rules_are_missing(tmp_path, monkeypatch, gate):
    gate()
    monkeypatch.setattr(merge_gate, "RULES", tmp_path / "absent.json")
    monkeypatch.setattr(sys, "argv", ["merge_gate.py", "7", "--enable"])
    monkeypatch.setattr(merge_gate.subprocess, "run", lambda *a, **k: pytest.fail("لا تفعيل عند خطأ"))
    assert merge_gate.main() == 2


def test_gate_enable_binds_auto_merge_to_the_measured_head(monkeypatch, gate):
    gate()
    calls = []
    monkeypatch.setattr(merge_gate.subprocess, "run", lambda cmd, **k: calls.append(cmd) or done())
    monkeypatch.setattr(sys, "argv", ["merge_gate.py", "7", "--repo", "owner/repo", "--enable"])
    assert merge_gate.main() == 0
    (cmd,) = calls
    assert cmd[cmd.index("--match-head-commit") + 1] == HEAD
    assert "--auto" in cmd


# ---------- فحص ما قبل الدفع


def test_changed_files_is_unmeasured_when_merge_base_fails(monkeypatch):
    monkeypatch.setattr(prepush_check, "run", lambda cmd, **k: done(returncode=128))
    assert prepush_check.changed_files("origin/main") is None


def test_changed_files_keeps_arabic_names_and_names_with_spaces(tmp_path, monkeypatch):
    names = ["laser/توريد الكفرات.md", "docs/a b.txt"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(prepush_check, "ROOT", tmp_path)

    def fake_run(cmd, **k):
        if cmd[1] == "merge-base":
            return done("abc123\n")
        assert "-z" in cmd
        return done("\0".join(names) + "\0" if cmd[1] == "diff" and "--cached" not in cmd else "")

    monkeypatch.setattr(prepush_check, "run", fake_run)
    assert prepush_check.changed_files("origin/main") == sorted(names)


def test_secrets_check_fails_without_a_file_list():
    assert prepush_check.check_secrets(None)[0] == prepush_check.FAIL


@pytest.mark.parametrize(
    ("proc", "expected"),
    [
        (done('{"results": {}}'), prepush_check.OK),
        (done('{"results": {"a.py": [{}]}}'), prepush_check.FAIL),
        (done("", returncode=1, stderr="Traceback"), prepush_check.FAIL),
        (done(""), prepush_check.FAIL),
        (done("{}"), prepush_check.FAIL),
        (done("", returncode=1, stderr="No module named detect_secrets"), prepush_check.MISSING),
    ],
)
def test_secrets_check_passes_only_on_a_clean_readable_scan(monkeypatch, proc, expected):
    monkeypatch.setattr(prepush_check, "run", lambda cmd, **k: proc)
    assert prepush_check.check_secrets(["a.py"])[0] == expected


def test_skip_leaves_no_success_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(prepush_check, "ROOT", tmp_path)
    monkeypatch.setattr(prepush_check, "run", lambda cmd, **k: done("abc\n"))
    for name in ("check_ruff", "check_format", "check_types", "check_migrations", "check_tests"):
        monkeypatch.setattr(prepush_check, name, lambda: (prepush_check.OK, ""))
    monkeypatch.setattr(prepush_check, "check_collisions", lambda base: (prepush_check.OK, ""))
    monkeypatch.setattr(prepush_check, "check_secrets", lambda files: (prepush_check.OK, ""))
    receipt = tmp_path / ".prepush_receipt"

    assert prepush_check.main([]) == 0
    assert json.loads(receipt.read_text(encoding="utf-8"))["head"] == "abc"
    # تشغيل ناقص بعد تشغيل كامل: يُزال الإيصال القديم ولا يُكتب جديد.
    assert prepush_check.main(["--skip", "tests"]) == 0
    assert not receipt.exists()


# ---------- تصادم الهجرات


def test_collisions_count_a_renamed_migration_in_an_open_pr(monkeypatch):
    def fake_gh(args):
        if args[0] == "pr":
            return [{"number": 5, "headRefName": "card/x", "headRefOid": "f" * 40}]
        return [
            [
                {"filename": "apps/orders/migrations/0004_b.py", "status": "renamed"},
                {"filename": "apps/orders/services.py", "status": "modified"},
            ]
        ]

    monkeypatch.setattr(collisions, "gh_json", fake_gh)
    (info,) = collisions.open_prs().values()
    assert info["files"] == ["apps/orders/migrations/0004_b.py"]
    found = collisions.find_collisions(["apps/orders/migrations/0004_a.py"], {"#5": info["files"]})
    assert [(app, num) for app, num, *_ in found] == [("apps/orders", "0004")]


def test_collisions_list_branch_files_without_rename_detection(monkeypatch):
    seen = []

    def fake_run(cmd):
        seen.append(cmd)
        return done("abc123\n" if cmd[1] == "merge-base" else "")

    monkeypatch.setattr(collisions, "run", fake_run)
    collisions.branch_added_paths("origin/main")
    (diff,) = [cmd for cmd in seen if cmd[1] == "diff"]
    assert "--no-renames" in diff


# ---------- المشغّل


@pytest.mark.parametrize(
    ("porcelain", "head", "ahead", "expected"),
    [
        ("", HEAD, "2", None),
        (" M apps/x.py", HEAD, "2", "dirty_tree"),
        ("", "b" * 40, "2", "head_moved"),
        ("", HEAD, "0", "no_commits"),
    ],
)
def test_runner_pushes_only_the_checked_clean_head_with_commits(
    monkeypatch, porcelain, head, ahead, expected
):
    answers = {"status": porcelain, "rev-parse": head, "rev-list": ahead}
    monkeypatch.setattr(runner, "sh", lambda cmd, **k: done(answers[cmd[1]] + "\n"))
    assert runner.unpushable(ROOT, HEAD) == expected


def test_runner_lock_is_exclusive_and_replaces_a_stale_one(tmp_path, monkeypatch):
    lock = tmp_path / ".lock"
    monkeypatch.setattr(runner, "LOCK", lock)
    assert runner.acquire_lock() is True
    assert lock.read_text(encoding="utf-8") == str(os.getpid())
    assert runner.acquire_lock() is False
    old = time.time() - runner.LOCK_STALE_SECONDS - 60
    os.utime(lock, (old, old))
    assert runner.acquire_lock() is True
    runner.release_lock()
    assert not lock.exists()


# ---------- حارس الغيت


def _guard():
    sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
    import guard_git

    return guard_git


@pytest.mark.parametrize(
    ("command", "tool", "allowed"),
    [
        ("GUARD_GIT_ALLOW='إذن المالك 2026-11-18' git push --force origin x", "Bash", True),
        ("GUARD_GIT_ALLOW='إذن المالك 2026-11-18' echo hi; git push --force origin x", "Bash", False),
        ("GUARD_GIT_ALLOW='إذن المالك 2026-11-18' git status; git push --force origin x", "Bash", False),
        ("$env:GUARD_GIT_ALLOW='إذن المالك 2026-11-18'; git push --force origin x", "PowerShell", True),
        ("git push --force origin x; $env:GUARD_GIT_ALLOW='إذن المالك 2026-11-18'", "PowerShell", False),
        ("git push --force origin x", "Bash", False),
    ],
)
def test_guard_override_covers_only_its_own_command(command, tool, allowed):
    guard = _guard()
    result = guard.check(
        command,
        tool=tool,
        cwd=str(ROOT),
        project_dir=str(ROOT),
        alias_lookup=lambda name: None,
        branch_lookup=lambda where: "claude/x",
    )
    assert result.hits
    assert bool(result.override) is allowed


def test_guard_sees_through_git_dir():
    guard = _guard()
    result = guard.check(
        "git --git-dir=D:/misk/.git push --force origin x",
        cwd=str(ROOT),
        project_dir=str(ROOT),
        alias_lookup=lambda name: None,
        branch_lookup=lambda where: "claude/x",
    )
    assert [hit.rule for hit in result.hits] == ["push-force"]
