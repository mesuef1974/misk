"""البوابات والمشغّل تفشل مغلقة: ما لم يُقَس لا يمرّ (docs/review-2026-11-16.md، القسم د)."""

import fnmatch
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

import approval  # noqa: E402
import check_migration_collisions as collisions  # noqa: E402
import merge_gate  # noqa: E402
import prepush_check  # noqa: E402
import runner  # noqa: E402

HEAD = "564d2a4b" + "0" * 32
APPROVED = "اعتُمد من المالك — 2026-11-18 — الرأس 564d2a4b"
GREEN = [{"name": name, "conclusion": "SUCCESS"} for name in ("بوابة الجودة", "approval-head", "scan")]
RULES_TEXT = (ROOT / "security" / "sensitive_paths.json").read_text(encoding="utf-8")


def done(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


# ---------- بوابة الدمج


@pytest.fixture
def gate(monkeypatch):
    """بوابة معزولة عن gh: الطلب وملفاته يُعطيان مباشرة."""

    def build(
        *,
        body=APPROVED,
        files=({"filename": "frontend/src/pages/HomePage.vue"},),
        checks=None,
        changed=None,
        rules=RULES_TEXT,
    ):
        pr = {
            "body": body,
            "headRefOid": HEAD,
            "baseRefName": "main",
            "changedFiles": len(files) if changed is None else changed,
            "statusCheckRollup": GREEN if checks is None else checks,
        }
        monkeypatch.setattr(merge_gate, "gh_json", lambda args: [list(files)] if args[0] == "api" else pr)
        monkeypatch.setattr(merge_gate, "base_rules", lambda repo, base: rules)
        return merge_gate.evaluate("7", "owner/repo")

    return build


def test_gate_allows_approved_green_ordinary_change(gate):
    assert gate() == (True, [], HEAD)


@pytest.mark.parametrize("state", ["STALE", "STARTUP_FAILURE", "FAILURE", "CANCELLED", "SOMETHING_NEW"])
def test_gate_blocks_any_state_it_does_not_know_as_passing(gate, state):
    ok, reasons, _ = gate(checks=[*GREEN, {"name": "scan", "conclusion": state}])
    assert not ok
    assert any("scan" in reason for reason in reasons)


@pytest.mark.parametrize("required", merge_gate.REQUIRED_CHECKS)
@pytest.mark.parametrize("state", ["SKIPPED", "NEUTRAL"])
def test_gate_does_not_count_a_skipped_mandatory_check_as_passing(gate, required, state):
    checks = [c for c in GREEN if c["name"] != required] + [{"name": required, "conclusion": state}]
    ok, reasons, _ = gate(checks=checks)
    assert not ok
    assert any(required in reason for reason in reasons)


def test_gate_still_accepts_a_skipped_optional_check(gate):
    assert gate(checks=[*GREEN, {"name": "معاينة اختيارية", "conclusion": "SKIPPED"}])[0]


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


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "apps/orders/CLAUDE.md",
        ".claude/rules/migrations.md",
        ".claude/agents/reviewer.md",
        ".claude/hooks/guard_deploy.py",
        "frontend/package.json",
        "config/urls.py",
        "config/celery.py",
        "migrations/0001_initial.py",
        "automation/ledger/card.jsonl",
    ],
)
def test_gate_forbids_paths_the_review_found_uncovered(gate, path):
    """ج6: تعليمات الوكلاء، وسكربتات npm، والمسارات والعامل، والهجرات في الجذر."""
    assert not gate(files=({"filename": path},))[0]


TEST_AND_BUILD_CONFIG = [
    "conftest.py",
    "apps/orders/tests/conftest.py",
    "pytest.ini",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "ruff.toml",
    "apps/core/.ruff.toml",
    "mypy.ini",
    # ز4: coverage يقف عند أول .coveragerc فيُسقط fail_under، وruff يأخذ بأقرب pyproject.toml.
    ".coveragerc",
    ".coveragerc.toml",
    "apps/x/pyproject.toml",
    "sitecustomize.py",
    "apps/core/evil.pth",
    "manage.py",
    "config/wsgi.py",
    "config/asgi.py",
    "frontend/vite.config.ts",
    "frontend/vitest.config.ts",
    "frontend/eslint.config.js",
    "frontend/playwright.config.ts",
    "frontend/.eslintrc.cjs",
    "frontend/tsconfig.json",
    "frontend/tsconfig.node.json",
    "frontend/.npmrc",
]


@pytest.mark.parametrize("path", TEST_AND_BUILD_CONFIG)
def test_gate_forbids_config_that_ci_executes(gate, path):
    """د3: الطلب يشغّل إعداده في CI (conftest يُنجح كل اختبار، وvite.config يُنفَّذ في البناء)، فلا دمج آلي له."""
    assert not gate(files=({"filename": path},))[0]


@pytest.mark.parametrize("path", TEST_AND_BUILD_CONFIG)
def test_sensitive_paths_workflow_asks_for_review_of_config_that_ci_executes(path):
    """د3: فحص sensitive-paths يطابق `mandatory_review_when_diff_touches` بـfnmatch كما في سير العمل."""
    categories = json.loads(RULES_TEXT)["mandatory_review_when_diff_touches"]
    assert any(fnmatch.fnmatch(path, glob) for glob in categories["test_and_build_config"])


@pytest.mark.parametrize("path", ["apps/orders/tests/test_api.py", "frontend/src/main.ts", "docs/setup.md"])
def test_gate_still_allows_ordinary_code_and_tests(gate, path):
    """الحظر على ملفات الإعداد لا يمتدّ إلى الشيفرة والاختبارات العادية."""
    assert merge_gate.path_forbidden(path, merge_gate.forbidden_globs(RULES_TEXT)) is None


def test_gate_stops_when_the_file_list_is_cut_short(gate):
    """ج5: واجهة الملفات تقف عند 3000؛ ما لم يُقرأ لا يُفترض نظيفًا."""
    with pytest.raises(merge_gate.GateError):
        gate(changed=2)
    many = tuple({"filename": f"docs/{index}.md"} for index in range(merge_gate.FILES_API_LIMIT))
    with pytest.raises(merge_gate.GateError):
        gate(files=many)


@pytest.mark.parametrize("missing", ["بوابة الجودة", "approval-head", "scan"])
def test_gate_requires_each_mandatory_check_by_name(gate, missing):
    """ج5: فحص إلزامي لم يُسجَّل بعد لا يمرّ بغيابه، ولو اخضرّ كل ما سُجّل."""
    ok, reasons, _ = gate(checks=[check for check in GREEN if check["name"] != missing])
    assert not ok
    assert any(missing in reason for reason in reasons)


def test_gate_reads_its_rules_from_the_base_branch(monkeypatch, gate):
    """ج5: القائمة من فرع الأساس على GitHub، لا من الشجرة التي قد يغيّرها الطلب."""
    calls = []
    monkeypatch.setattr(
        merge_gate.subprocess,
        "run",
        lambda cmd, **k: calls.append(cmd) or done(RULES_TEXT),
    )
    assert merge_gate.base_rules("owner/repo", "main") == RULES_TEXT
    (cmd,) = calls
    assert cmd[-1] == "repos/owner/repo/contents/security/sensitive_paths.json?ref=main"
    monkeypatch.setattr(merge_gate.subprocess, "run", lambda cmd, **k: done(returncode=1, stderr="404"))
    with pytest.raises(merge_gate.GateError):
        merge_gate.base_rules("owner/repo", "main")


@pytest.mark.parametrize("flag", ["--ena", "--enab", "--e"])
def test_gate_refuses_abbreviated_enable(monkeypatch, gate, flag):
    """ج1: argparse كان يقبل `--ena` اختصارًا لـ`--enable` فيلتفّ على قاعدة deny."""
    gate()
    monkeypatch.setattr(sys, "argv", ["merge_gate.py", "7", flag])
    monkeypatch.setattr(merge_gate.subprocess, "run", lambda *a, **k: pytest.fail("لا تفعيل باختصار"))
    with pytest.raises(SystemExit):
        merge_gate.main()


def test_gate_blocks_without_approval_or_on_a_stale_head(gate):
    assert not gate(body="")[0]
    assert not gate(body="اعتُمد من المالك — 2026-11-18 — الرأس aaaaaaaa")[0]


LINE = "اعتُمد من المالك — 2026-11-20 — الرأس 7e3477d3"


@pytest.mark.parametrize(
    "body",
    [
        f"وصف\n\n{LINE}\n",
        f"وصف\r\n\r\n{LINE}\r\n",
        f"  {LINE}  ",
        f"<!-- مخفي -->\n{LINE}",
        f"```\nشيفرة\n```\n{LINE}",
        # ز6: محارف الاتجاه والمسافة التي لا تنكسر تُدرجها محررات العربية ولا تُرى.
        f"{LINE}‏",
        f"‏{LINE}‎\n",
        f" {LINE}",
        "اعتُمد من المالك — 2026-11-20 — الرأس 7e3477d3",
        f"⁧{LINE}⁩",
    ],
)
def test_approval_line_on_its_own_visible_line_counts(body):
    assert approval.approved_heads(body) == ["7e3477d3"]


@pytest.mark.parametrize(
    "body",
    [
        f"وصف\n<!-- {LINE} -->",
        f"وصف\n<!--\n{LINE}\n-->",
        f"وصف\n<!--\n{LINE}",
        f"```\n{LINE}\n```",
        f"~~~text\n{LINE}\n~~~",
        f"```\n{LINE}",
        f"`{LINE}`",
        f"لا تكتب {LINE} قبل المراجعة",
        f"[{LINE}](https://example.com)",
        f"<span>{LINE}</span>",
        f"> {LINE}",
        # ز6: السطر المزاح بأربع مسافات أو بجدولة تعرضه الصفحة كتلة شيفرة.
        f"وصف\n\n    {LINE}",
        f"    {LINE}",
        f"\t{LINE}",
        f"  \t{LINE}",
        f"‏    {LINE}",
    ],
)
def test_approval_line_hidden_or_embedded_does_not_count(body, gate):
    """د4: تعليق HTML وكتلة الشيفرة لا تعرضهما الصفحة سطرًا، والسطر داخل جملة أو وسم ليس اعتمادًا."""
    assert approval.approved_heads(body) == []
    assert not gate(body=body)[0]


@pytest.mark.parametrize("content", ["", "{", "{}", '{"forbidden_for_auto_merge": []}'])
def test_gate_stops_when_the_rules_file_is_missing_or_broken(content):
    with pytest.raises(merge_gate.GateError):
        merge_gate.forbidden_globs(content)


def test_gate_main_reports_an_error_not_a_pass_when_rules_are_missing(monkeypatch, gate):
    gate()
    monkeypatch.setattr(merge_gate, "base_rules", lambda repo, base: "")
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


def _runner_tree(monkeypatch, *, diff=(), untracked=(), rules=RULES_TEXT):
    answers = {"show": rules, "diff": "\0".join(diff), "ls-files": "\0".join(untracked)}
    monkeypatch.setattr(runner, "sh", lambda cmd, **k: done(answers[cmd[1]]))


@pytest.mark.parametrize(
    ("diff", "untracked", "expected"),
    [
        (["apps/orders/services.py"], [], []),
        (["scripts/prepush_check.py"], [], ["scripts/prepush_check.py"]),
        (["apps/x.py"], [".claude/hooks/extra.py"], [".claude/hooks/extra.py"]),
        (["CLAUDE.md", "apps/x.py"], [], ["CLAUDE.md"]),
    ],
)
def test_runner_finds_forbidden_paths_committed_or_not(monkeypatch, diff, untracked, expected):
    """ج2: الفاحص في الـ worktree يكتبه النموذج؛ فرق يمسّ مسارًا محظورًا يُرفض قبل تشغيله."""
    _runner_tree(monkeypatch, diff=diff, untracked=untracked)
    assert runner.touched_forbidden(ROOT) == expected


def test_runner_does_not_check_or_push_a_diff_touching_forbidden_paths(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(runner, "pick_card", lambda: "c1")
    monkeypatch.setattr(runner, "acquire_lock", lambda: True)
    monkeypatch.setattr(runner, "release_lock", lambda: None)
    monkeypatch.setattr(runner, "make_worktree", lambda card, env=None: (ROOT, "card/c1"))
    monkeypatch.setattr(runner, "STATE", tmp_path / "state")
    monkeypatch.setattr(runner, "baseline_drift", lambda: None)
    monkeypatch.setattr(runner, "run_model", lambda *a, **k: 0)
    monkeypatch.setattr(runner.ledger, "append", lambda card, event, **data: events.append((event, data)))
    monkeypatch.setattr(runner, "touched_forbidden", lambda path, env=None: ["scripts/prepush_check.py"])
    monkeypatch.setattr(runner, "prepush", lambda path, env=None: pytest.fail("لا فحص بفاحص عدّله النموذج"))
    monkeypatch.setattr(runner, "push_and_open_pr", lambda *a: pytest.fail("لا دفع"))
    monkeypatch.setattr(runner, "sh", lambda cmd, **k: done(HEAD))
    assert runner.main([]) == 1
    assert events[-1] == (
        "blocked",
        {"reason": "forbidden_paths", "head": HEAD, "paths": ["scripts/prepush_check.py"]},
    )


def test_runner_blocks_when_the_rules_cannot_be_read(monkeypatch):
    _runner_tree(monkeypatch, rules="")
    with pytest.raises(merge_gate.GateError):
        runner.touched_forbidden(ROOT)


def test_runner_records_push_blockers_as_known_ledger_states():
    """«dirty_tree» وأخواتها ليست حالات في الدفتر؛ كانت ترمي ValueError بدل أن تُسجَّل."""
    for reason in ("dirty_tree", "head_moved", "no_commits", "forbidden_paths"):
        assert reason not in runner.ledger.STATES
    assert "blocked" in runner.ledger.STATES


@pytest.mark.parametrize(
    "tool",
    [
        "Bash(git -C . push origin x)",
        "Bash(gh api repos/o/r/pulls/1/merge -X PUT)",
        "Bash(npx @railway/cli up)",
    ],
)
def test_runner_denies_the_known_bypasses(tool):
    """ج2: البادئات `git -C` و`gh api` و`npx @railway/cli` كانت تمرّ من قائمة الأدوات الممنوعة."""
    import fnmatch

    assert any(fnmatch.fnmatchcase(tool, rule) for rule in runner.DISALLOWED_TOOLS)


@pytest.mark.parametrize(
    ("stderr", "missing"),
    [
        ("/usr/bin/python: No module named mypy\n", True),
        ("ModuleNotFoundError: No module named 'mypy'", True),
        ("ModuleNotFoundError: No module named 'apps.missing'", False),
        ("No module named mypy_extensions", False),
    ],
)
def test_prepush_counts_only_the_tool_itself_as_missing(stderr, missing):
    """ج7: وحدة غائبة في الشيفرة المفحوصة فشل يُبلَّغ، لا أداة غائبة تُتخطّى."""
    assert prepush_check.module_missing(done(returncode=1, stderr=stderr), "mypy") is missing


def test_worker_script_waits_for_migrations_and_parses():
    """ج4: العامل لا يبدأ قبل أن تُطبَّق هجرات preDeploy الويب."""
    script = (ROOT / "scripts" / "railway-worker.sh").read_text(encoding="utf-8")
    assert script.index("manage.py pending_migrations") < script.index("exec celery")
    shell = __import__("shutil").which("sh")
    if shell:
        assert subprocess.run([shell, "-n", str(ROOT / "scripts" / "railway-worker.sh")]).returncode == 0


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


# ---------- حارس الدمج والنشر


def _deploy_guard():
    sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
    import guard_deploy

    return guard_deploy


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        ("gh pr merge 39 --squash", "gh-pr-merge"),
        ("cd x && gh  pr   merge 39", "gh-pr-merge"),
        ("gh api repos/o/r/pulls/39/merge -X PUT", "gh-api-merge"),
        (
            "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }'",
            "gh-api-merge",
        ),
        ("railway up", "railway-cli"),
        ("RAILWAY_TOKEN=x railway config apply", "railway-cli"),
        ("C:/tools/railway.exe variables", "railway-cli"),
        ("npx @railway/cli up", "railway-npm"),
        ("npm exec --yes @railway/cli -- up", "railway-npm"),
        ("python scripts/merge_gate.py 39 --ena", "merge-gate-enable"),
        ("python scripts/merge_gate.py 39 --enable", "merge-gate-enable"),
    ],
)
def test_deploy_guard_blocks_merge_and_deploy_in_any_form(command, rule):
    """ج1: قواعد deny تطابق البادئة؛ الحارس يبحث في الأمر كله."""
    assert rule in _deploy_guard().hits(command)


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        # الاسم المستعار يُحفظ في إعداد gh فيبقى للجلسات التالية.
        ("gh alias set m 'pr merge'", "gh-alias"),
        ("gh alias import aliases.yml", "gh-alias"),
        # الاستعلام من ملف لا يُرى نصّه في الأمر.
        ("gh api graphql -F query=@q.graphql", "gh-api-graphql"),
        ("gh api graphql --input body.json", "gh-api-graphql"),
        # مسار يُبنى بمتغيّر أو جسم من ملف.
        ("m=mer; gh api -X PUT repos/o/r/pulls/5/${m}ge", "gh-api-indirect"),
        ("gh api -X PUT repos/o/r/pulls/5/$(echo merge)", "gh-api-indirect"),
        ("gh api repos/o/r/pulls/5 --input body.json", "gh-api-indirect"),
        ("gh api repos/o/r/pulls/5 -F x=@f", "gh-api-indirect"),
        # كلمة تُركَّب من متغيّر أو أقواس تلتصق بحروف.
        ("r=rail; ${r}way up", "glued-expansion"),
        ("$(echo rail)way up", "glued-expansion"),
        ("rail''way up", "glued-expansion"),
        ('g""h pr merge 5', "glued-expansion"),
        # شيفرة تُمرَّر إلى مفسّر وتذكر gh أو railway.
        ("python -c \"import subprocess; subprocess.run(['gh','pr','mer'+'ge','5'])\"", "inline-interpreter"),
        ("node -e \"require('child_process').execSync('gh pr mer'+'ge 5')\"", "inline-interpreter"),
        ("bash -c 'g=gh; $g pr view 5'", "inline-interpreter"),
        ("pwsh -Command \"& ('rail'+'way') up\"", "inline-interpreter"),
        ("python - <<'EOF'\nimport os; os.system('gh pr mer' + 'ge 5')\nEOF", "inline-interpreter"),
        ("iex \"gh pr mer$('ge') 5\"", "inline-interpreter"),
    ],
)
def test_deploy_guard_blocks_the_bypasses_review_d1_found(command, rule):
    """د1 (مراجعة 2026-11-19 الثانية): التفافات خرجت بـ0 من الحارس."""
    assert rule in _deploy_guard().hits(command)


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        # علم عام بين gh والأمر الفرعي.
        ("gh -R o/r pr merge 5", "gh-pr-merge"),
        ("gh --repo o/r pr merge 5", "gh-pr-merge"),
        ("gh --repo=o/r pr merge 5 --squash", "gh-pr-merge"),
        ("gh -R o/r api -X PUT repos/o/r/pulls/5/merge", "gh-api-merge"),
        ("gh -R o/r alias set m 'pr merge'", "gh-alias"),
        ("gh api --method POST graphql -f query=@q", "gh-api-graphql"),
        # تنصيص وهروب داخل الكلمة.
        ('gh pr "merge" 5', "gh-pr-merge"),
        ("gh pr mer\\ge 5", "gh-pr-merge"),
        ('gh api -X PUT repos/o/r/pulls/5/me"rg"e', "gh-api-merge"),
        ("rail\\way up", "railway-cli"),
        ("'rail'way up", "railway-cli"),
        # متغيّر ملتصق بحروف بلا أقواس.
        ('r=rail; "$r"way up', "glued-expansion"),
        ("w=way; rail$w up", "glued-expansion"),
        ('w=way; rail"$w" up', "glued-expansion"),
        # الرمز نفسه.
        ('curl -X PUT -H "Authorization: token $(gh auth token)" https://api.github.com/x', "token-read"),
        ("gh auth status --show-token", "token-read"),
        ("gh auth status -t", "token-read"),
        ("gh auth git-credential get", "token-read"),
        ("printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill", "token-read"),
        ("git-credential-manager.exe get", "token-read"),
        # شيفرة مفسّر تستدعي عملية فرعية باسم مبني بالجمع.
        ("node -e \"require('child_process').execSync('g'+'h pr mer'+'ge 5')\"", "inline-interpreter"),
        ("python -c \"import subprocess as s; s.run(['g'+'h', 'pr'])\"", "inline-interpreter"),
        ("pwsh -Command \"Start-Process ('g'+'h')\"", "inline-interpreter"),
        # heredoc غير منصَّص يوسّع $(…)، وheredoc يُمرَّر إلى صدفة: كلاهما أمر لا بيانات.
        ("cat > x.md <<EOF\n$(gh pr merge 5)\nEOF", "gh-pr-merge"),
        ("cat <<'EOF' | bash\ngh pr merge 5\nEOF", "gh-pr-merge"),
    ],
)
def test_deploy_guard_blocks_the_bypasses_review_z1_found(command, rule):
    """ز1 (مراجعة 2026-11-20): التفافات خرجت بـ0 بعد تخفيف د1."""
    assert rule in _deploy_guard().hits(command)


@pytest.mark.parametrize(
    "command",
    [
        # كلمة مركَّبة في وسيط لا في موضع الأمر، ولا كلمة نشر.
        "for f in a b; do cp ${f}.txt ${f}bak; done",
        'echo "x$(git rev-parse HEAD)"',
        'echo "build-$(date +%s)" > stamp',
        # ملفات المستودع التي يحمل اسمها rail.
        "bash -c 'bash scripts/railway-worker.sh'",
        'bash -c "sed -n 1,20p .railway/railway.ts"',
        "sh -c 'grep -rn version frontend/node_modules/railway/package.json'",
        # نص heredoc حرفي يُكتب إلى ملف: بيانات لا أمر.
        "cat > \"$S/pr.md\" <<'EOF'\nكان التوثيق يقول إن المكشوف SSH وإعداد railway وحدهما، و- `gh pr merge` محجوب.\nEOF\n"
        'gh pr create --title t --body-file "$S/pr.md"',
        'tee notes.md >/dev/null <<"EOF"\nrailway up\nEOF',
        # مفسّر بلا عملية فرعية ولا كلمة نشر.
        "python -c \"import json; print(json.dumps({'a': 1}))\"",
        # قراءة حالة gh لا تطبع الرمز.
        "gh auth status",
        "gh pr view 70 --repo o/r --json headRefOid --jq .headRefOid",
    ],
)
def test_deploy_guard_allows_what_review_z5_found_blocked(command):
    """ز5 (مراجعة 2026-11-20): إيجابيات كاذبة حجبت عملًا مشروعًا."""
    assert _deploy_guard().hits(command) == []


@pytest.mark.parametrize(
    "command",
    [
        "cat .railway/railway.ts",
        "bash scripts/railway-worker.sh",
        "sh -n scripts/railway-predeploy.sh",
        "gh pr view 39 --json mergeable",
        "gh pr checks 39",
        "python scripts/merge_gate.py 39",
        "git merge --ff-only origin/main",
        "python -m pytest tests/test_gates.py",
        # ما تشغّله الجلسة عادةً ولا يذكر gh ولا railway في شيفرة مفسّر.
        "gh pr view 52 --repo o/r --json body --jq .body",
        'gh pr edit 52 --body-file "$S/b52.md"',
        "python -c \"print('ok')\"",
        "python - <<'EOF'\nprint(open('README.md').read())\nEOF",
        'PATH="/d/misk/.venv/Scripts:$PATH" python scripts/prepush_check.py --frontend',
        'cp "$S/pp.vue" frontend/src/pages/ProductionPage.vue',
        "echo ${HOME}/x",
    ],
)
def test_deploy_guard_allows_reading_and_checking(command):
    assert _deploy_guard().hits(command) == []


def test_deploy_guard_hook_exit_codes(monkeypatch, capsys):
    guard = _deploy_guard()
    for command, code in (("gh pr merge 1", 2), ("gh pr view 1", 0)):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(payload))
        assert guard.main() == code
    assert "gh-pr-merge" in capsys.readouterr().err


# مركَّب لا حرفي، كـHEAD أعلاه: سلسلة 40 خانة ست عشرية حرفية يعدّها detect-secrets سرًّا.
_SHA = "f12cccbd" + "0" * 32


def test_deploy_guard_sends_the_one_merge_form_to_the_owner_prompt(monkeypatch, capsys):
    """قرار المالك 2026-11-21: الصيغة المربوطة بالرأس لا تُسمح ولا تُحجب، بل تُحال إلى نافذة الموافقة."""
    guard = _deploy_guard()
    command = f"gh pr merge 88 --squash --match-head-commit {_SHA}"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(payload))
    assert guard.main() == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "ask"
    assert "88" in out["permissionDecisionReason"] and _SHA[:8] in out["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 88 --squash",
        f"gh pr merge 88 --squash --match-head-commit {_SHA[:8]}",
        f"gh pr merge 88 --squash --match-head-commit {_SHA} --admin",
        f"gh pr merge 88 --squash --auto --match-head-commit {_SHA}",
        f"gh pr merge 88 --merge --match-head-commit {_SHA}",
        f"gh -R o/r pr merge 88 --squash --match-head-commit {_SHA}",
        f"gh pr merge 88 --squash --match-head-commit {_SHA} && gh pr merge 89 --squash",
        f"gh pr merge 88 --squash --match-head-commit {_SHA}\ngh pr merge 89 --squash",
        f"gh pr merge 88 --squash --match-head-commit {_SHA}; railway up",
        f"gh pr merge $(echo 88) --squash --match-head-commit {_SHA}",
        f"gh pr merge feat/x --squash --match-head-commit {_SHA}",
        f'gh pr "merge" 88 --squash --match-head-commit {_SHA}',
    ],
)
def test_deploy_guard_still_blocks_every_other_merge_form(command, monkeypatch, capsys):
    guard = _deploy_guard()
    assert guard.owner_merge(command) is None
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(payload))
    assert guard.main() == 2
    assert capsys.readouterr().out == ""


def test_merge_is_ask_not_deny_and_deploy_stays_denied():
    permissions = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]
    assert "Bash(gh pr merge*)" in permissions["ask"]
    assert not [rule for rule in permissions["deny"] if "merge*)" in rule and "gate" not in rule]
    assert not [rule for rule in permissions.get("allow", []) if "merge" in rule or "railway" in rule]
    for rule in ("Bash(railway *)", "Bash(*@railway/cli*)", "Bash(*merge_gate.py*--enable*)"):
        assert rule in permissions["deny"]


def test_deploy_guard_is_registered_for_bash_and_powershell():
    hooks = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"][
        "PreToolUse"
    ]
    (entry,) = [h for h in hooks if "guard_deploy.sh" in json.dumps(h)]
    assert entry["matcher"] == "Bash|PowerShell"
