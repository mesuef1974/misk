"""سير عمل المسارات الحسّاسة يُشغَّل كما هو على مستودع مؤقت: ما يكتبه في الطلب هو ما يقيسه الاختبار."""

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sensitive-paths.yml"
RULES = {
    "mandatory_review_when_diff_touches": {"security": ["security/*"]},
    "mandatory_review_when_diff_content_matches": {"secrets": ["SECRET_[A-Z]+_X"]},
}


def workflow_script() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    body = re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", text, re.S)
    assert body, "لم يُعثر على سكربت الفحص في سير العمل"
    return textwrap.dedent(body.group(1))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """يبني أساسًا فيه قواعد، ثم رأسًا فيه الملفات المعطاة، ويشغّل السكربت ويعيد تعليقه."""

    def run(files: dict[str, str]) -> str:
        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "security").mkdir()
        (repo / "security" / "sensitive_paths.json").write_text(json.dumps(RULES), encoding="utf-8")
        git(repo, "add", "security/sensitive_paths.json")
        git(repo, "commit", "-q", "-m", "base")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        for name, content in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            git(repo, "add", "--", name)
        git(repo, "commit", "-q", "-m", "head")

        comments: list[str] = []
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                if cmd[1:3] == ["pr", "comment"]:
                    comments.append(cmd[cmd.index("--body") + 1])
                return subprocess.CompletedProcess(cmd, 0)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.chdir(repo)
        monkeypatch.setenv("BASE", "main")
        monkeypatch.setenv("PR", "7")
        monkeypatch.setattr(subprocess, "run", fake_run)
        exec(compile(workflow_script(), str(WORKFLOW), "exec"), {"__name__": "__main__"})
        return "\n".join(comments)

    return run


@pytest.mark.parametrize("name", ["docs/ملاحظات المراجعة.md", "وثائق/سر.py", "docs/plain.md"])
def test_content_scan_sees_added_lines_in_arabic_and_spaced_names(scan, name):
    """د6: git يقتبس الأسماء العربية افتراضًا ("b/\\330...")، فكان فحص المحتوى يتخطّاها."""
    comment = scan({name: "token = SECRET_ABC_X\n"})
    assert "secrets" in comment
    assert name in comment


def test_clean_change_gets_no_comment(scan):
    assert scan({"وثائق/عادي.md": "نص عادي\n"}) == ""
