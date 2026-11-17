#!/usr/bin/env python3
"""بوابة الدمج: تقرّر هل يُدمج طلب معيّن دون يد المالك أم يبقى يدويًا، وتدمجه إن طُلب منها ذلك.

هي الطريق الوحيد للدمج من الجلسة (قرار المالك 2026-11-17): `gh pr merge` المباشر يبقى محجوبًا في
`.claude/settings.json`، والجلسة تدمج بـ `--merge` هنا فلا يمرّ إلا ما استوفى الشروط.

الشروط (كلها لازمة):
  1. سطر اعتماد المالك في وصف الطلب مربوط برأس الطلب الحالي (scripts/approval.py).
  2. لا ملف متغيّر يطابق المسارات المحظورة (security/sensitive_paths.json → forbidden_for_auto_merge).
     ملفات CI والـ lockfiles وسكربتات البوابات نفسها محظورة دائمًا: النموذج لا يعدّل حارسه.
  3. لا سطر متغيّر يمسّ المال (forbidden_for_auto_merge_content): الأسعار والمبالغ والدفع تُدمج بيد المالك.
  4. كل فحوص CI خضراء (لا PENDING ولا FAILURE)، بآخر تشغيل لكل فحص.
  5. مع `--merge`: خارج نافذة النشر (scripts/deploy_window.py) أو الطلب موسوم «نشر-عاجل».

القواعد تُقرأ من origin/main لا من الشجرة المحلية، حتى لا يليّنها فرع العمل.

الاستعمال:  python scripts/merge_gate.py <رقم الطلب> [--repo owner/name] [--merge | --enable]
  --merge   دمج بالضغط (squash) مربوط بالرأس المعتمد: إن تغيّر الرأس بعد الفحص رفض GitHub الدمج.
  --enable  تفعيل auto-merge لطابور الدمج (للمشغّل).
الخروج:     0 مسموح (أو دُمج/فُعِّل)، 1 ممنوع يبقى يدويًا، 2 خطأ gh/شبكة.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_window  # noqa: E402
from approval import approved_heads, same_head  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "security" / "sensitive_paths.json"

ALWAYS_FORBIDDEN = (
    ".github/*",
    ".github/**",
    "scripts/merge_gate.py",
    "scripts/approval.py",
    "scripts/pr_approval_head_check.py",
    "scripts/prepush_check.py",
    "security/*",
    ".claude/hooks/*",
    ".claude/settings.json",
    "package-lock.json",
    "frontend/package-lock.json",
    "requirements*.txt",
    "Dockerfile",
    "railway.toml",
)
FAILING = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}
PENDING = {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "REQUESTED", "WAITING"}


def gh_json(args: list[str]) -> dict:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def load_rules() -> dict:
    """قواعد فرع الأساس إن وُجد محليًّا (origin/main)، وإلا ملف الشجرة."""
    base = subprocess.run(
        ["git", "-C", str(ROOT), "show", "origin/main:security/sensitive_paths.json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if base.returncode == 0 and base.stdout.strip():
        return json.loads(base.stdout)
    if RULES.exists():
        return json.loads(RULES.read_text(encoding="utf-8"))
    return {}


def forbidden_globs(rules: dict | None = None) -> tuple[str, ...]:
    rules = load_rules() if rules is None else rules
    return ALWAYS_FORBIDDEN + tuple(rules.get("forbidden_for_auto_merge", []))


def changed_lines(diff: str) -> list[tuple[str, str]]:
    """(المسار، السطر) لكل سطر مضاف أو محذوف في فرق موحَّد."""
    out: list[tuple[str, str]] = []
    path = ""
    for line in diff.splitlines():
        if line.startswith(("+++ ", "--- ")):
            name = line[4:].strip()
            if name != "/dev/null":
                path = name[2:] if name[:2] in ("a/", "b/") else name
        elif line[:1] in ("+", "-") and path:
            out.append((path, line[1:]))
    return out


def content_hits(diff: str, rules: dict) -> list[str]:
    """أسباب المنع من محتوى الفرق: لكل فئة، أول سطر مطابق في كل ملف."""
    hits: list[str] = []
    lines = changed_lines(diff)
    for category, rule in (rules.get("forbidden_for_auto_merge_content") or {}).items():
        globs = rule.get("paths") or ["*"]
        patterns = [re.compile(p) for p in rule.get("patterns", [])]
        seen: set[str] = set()
        for path, text in lines:
            if path in seen or not any(fnmatch.fnmatch(path, g) for g in globs):
                continue
            match = next((m for m in (p.search(text) for p in patterns) if m), None)
            if match:
                seen.add(path)
                hits.append(f"{category}: {path} («{match.group(0)}»)")
    return hits


def latest_checks(checks: list[dict]) -> list[dict]:
    """آخر تشغيل لكل فحص: إعادة التشغيل تُبقي القديم الفاشل في القائمة ولا يُحسب."""

    def stamp(check: dict) -> str:
        return check.get("startedAt") or check.get("completedAt") or ""

    latest: dict[str, dict] = {}
    for c in checks:
        name = c.get("name") or c.get("context") or "؟"
        if name not in latest or stamp(c) >= stamp(latest[name]):
            latest[name] = c
    return list(latest.values())


def window_reason(labels: list[str], now: datetime) -> str | None:
    """الدمج نشر فوري: ممنوع وقت الدوام إلا بوسم الإصلاح العاجل."""
    if not deploy_window.in_work_hours(now) or deploy_window.LABEL in labels:
        return None
    end = f"{deploy_window.WINDOW_END_HOUR}:00"
    return (
        f"نافذة النشر: وقت الدوام والدمج نشر فوري. أعد بعد {end} أو يوسم المالك الطلب «{deploy_window.LABEL}»"
    )


def path_forbidden(path: str, globs: tuple[str, ...]) -> str | None:
    for pattern in globs:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.lower(), pattern.lower()):
            return pattern
    return None


def evaluate(pr: str, repo: str | None, merging: bool = False) -> tuple[bool, list[str], str]:
    reasons: list[str] = []
    args = ["pr", "view", pr, "--json", "body,files,statusCheckRollup,headRefOid,labels,state,isDraft"]
    if repo:
        args += ["--repo", repo]
    data = gh_json(args)
    rules = load_rules()

    head = data.get("headRefOid") or ""
    if data.get("state") != "OPEN" or data.get("isDraft"):
        reasons.append("الطلب ليس مفتوحًا جاهزًا (مغلق أو مسودة)")
    heads = approved_heads(data.get("body") or "")
    if not heads:
        reasons.append("لا سطر اعتماد («اعتُمد من المالك — YYYY-MM-DD — الرأس sha8») في وصف الطلب")
    elif not any(same_head(h, head) for h in heads):
        reasons.append(
            f"سطر الاعتماد على رأس قديم ({', '.join(h[:8] for h in heads)})، والرأس الحالي {head[:8]}"
        )

    globs = forbidden_globs(rules)
    blocked = []
    for f in data.get("files") or []:
        path = f.get("path", "")
        pattern = path_forbidden(path, globs)
        if pattern:
            blocked.append(f"{path} ({pattern})")
    if blocked:
        reasons.append("مسارات محظورة على الدمج الآلي: " + "، ".join(blocked))

    diff_cmd = ["gh", "pr", "diff", pr] + (["--repo", repo] if repo else [])
    diff = subprocess.run(diff_cmd, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    content = content_hits(diff, rules)
    if content:
        reasons.append("محتوى محظور على الدمج الآلي: " + "، ".join(content))

    if merging:
        labels = [label.get("name", "") for label in data.get("labels") or []]
        window = window_reason(labels, datetime.now(UTC))
        if window:
            reasons.append(window)

    checks = latest_checks(data.get("statusCheckRollup") or [])
    if not checks:
        reasons.append("لا فحوص CI مسجّلة على الطلب بعد")
    for c in checks:
        state = (c.get("conclusion") or c.get("state") or "").upper()
        name = c.get("name") or c.get("context") or "؟"
        if state in FAILING:
            reasons.append(f"فحص فاشل: {name}")
        elif state in PENDING or not state:
            reasons.append(f"فحص لم يكتمل: {name}")
    return (not reasons), reasons, head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pr")
    ap.add_argument("--repo")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    try:
        ok, reasons, head = evaluate(args.pr, args.repo, merging=args.merge)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 2
    if ok:
        print(f"[مسموح] الطلب #{args.pr} يستوفي شروط الدمج الآلي")
        if args.enable:
            cmd = ["gh", "pr", "merge", args.pr, "--auto"] + (["--repo", args.repo] if args.repo else [])
            subprocess.run(cmd, check=True)
            print("[تفعيل] auto-merge مفعّل؛ طابور الدمج يتولّى الباقي")
        if args.merge:
            cmd = ["gh", "pr", "merge", args.pr, "--squash", "--match-head-commit", head]
            done = subprocess.run(cmd + (["--repo", args.repo] if args.repo else []), check=False)
            if done.returncode != 0:
                print("[خطأ] رفض GitHub الدمج (تغيّر الرأس أو قاعدة حماية)", file=sys.stderr)
                return 2
            print(f"[دُمج] الطلب #{args.pr} عند الرأس {head[:8]}")
        return 0
    print(f"[ممنوع] الطلب #{args.pr} يبقى دمجًا يدويًا:")
    for r in reasons:
        print(f"  - {r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
