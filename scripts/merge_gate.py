#!/usr/bin/env python3
"""بوابة الدمج الآلي: تقرّر هل يُفعَّل `gh pr merge --auto` على طلب معيّن أم يبقى يدويًا. لا تدمج بنفسها.

الشروط (كلها لازمة):
  1. سطر اعتماد المالك في وصف الطلب مربوط برأس الطلب الحالي (scripts/approval.py).
  2. لا ملف متغيّر يطابق المسارات المحظورة (security/sensitive_paths.json → forbidden_for_auto_merge).
     ملفات CI والـ lockfiles وسكربتات البوابات نفسها محظورة دائمًا: النموذج لا يعدّل حارسه.
  3. كل فحوص CI خضراء: الحالة الناجحة المعروفة وحدها تمرّ، وكل حالة غيرها تمنع.

الاعتماد نص في وصف الطلب ولا يُتحقق من كاتبه: الجلسة تعمل بحساب المالك نفسه على GitHub، فلا هوية ثانية تُقارن.
الضابط إجرائي: لا يكتب السطرَ غيرُ المالك، أو الجلسة بأمره الصريح لكل رأس (CLAUDE.md).

الاستعمال:  python scripts/merge_gate.py <رقم الطلب> [--repo owner/name] [--enable]
الخروج:     0 مسموح (أو فُعِّل)، 1 ممنوع يبقى يدويًا، 2 خطأ gh/شبكة.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    "scripts/check_migration_collisions.py",
    "scripts/railway-*.sh",
    "automation/*",
    "pyproject.toml",
    ".dockerignore",
    "security/*",
    ".claude/hooks/*",
    ".claude/settings.json",
    "package-lock.json",
    "frontend/package-lock.json",
    "requirements*.txt",
    "Dockerfile",
    ".railway/*",
    ".railway/**",
    "railway.toml",
    "railway.json",
)
PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}
PENDING = {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "REQUESTED", "WAITING"}


class GateError(Exception):
    """تعذّر قياس شرط؛ البوابة لا تسمح بما لم تقسه."""


def gh_json(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def forbidden_globs() -> tuple[str, ...]:
    """قائمة الحظر من الملف؛ غيابه أو فساده يوقف البوابة ولا يُسقط الحظر."""
    try:
        extra = json.loads(RULES.read_text(encoding="utf-8"))["forbidden_for_auto_merge"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GateError(f"تعذّرت قراءة {RULES.name}: {exc}") from exc
    if not isinstance(extra, list) or not extra:
        raise GateError(f"{RULES.name}: forbidden_for_auto_merge فارغة أو ليست قائمة")
    return ALWAYS_FORBIDDEN + tuple(extra)


def changed_paths(pr: str, repo: str | None) -> list[str]:
    """مسارات الطلب من واجهة الملفات: الاسم الجديد والقديم معًا، فإعادة التسمية لا تخفي مسارًا محظورًا."""
    target = repo or "{owner}/{repo}"
    pages = gh_json(["api", f"repos/{target}/pulls/{pr}/files", "--paginate", "--slurp"])
    paths: list[str] = []
    for page in pages or []:
        for item in page:
            paths += [p for p in (item.get("filename"), item.get("previous_filename")) if p]
    return sorted(set(paths))


def path_forbidden(path: str, globs: tuple[str, ...]) -> str | None:
    for pattern in globs:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.lower(), pattern.lower()):
            return pattern
    return None


def evaluate(pr: str, repo: str | None) -> tuple[bool, list[str], str]:
    reasons: list[str] = []
    args = ["pr", "view", pr, "--json", "body,statusCheckRollup,headRefOid"]
    if repo:
        args += ["--repo", repo]
    data = gh_json(args)

    head = data.get("headRefOid") or ""
    heads = approved_heads(data.get("body") or "")
    if not heads:
        reasons.append("لا سطر اعتماد («اعتُمد من المالك — YYYY-MM-DD — الرأس sha8») في وصف الطلب")
    elif not any(same_head(h, head) for h in heads):
        reasons.append(
            f"سطر الاعتماد على رأس قديم ({', '.join(h[:8] for h in heads)})، والرأس الحالي {head[:8]}"
        )

    globs = forbidden_globs()
    paths = changed_paths(pr, repo)
    if not paths:
        reasons.append("لا ملفات متغيّرة مقروءة من الطلب")
    blocked = []
    for path in paths:
        pattern = path_forbidden(path, globs)
        if pattern:
            blocked.append(f"{path} ({pattern})")
    if blocked:
        reasons.append("مسارات محظورة على الدمج الآلي: " + "، ".join(blocked))

    checks = data.get("statusCheckRollup") or []
    if not checks:
        reasons.append("لا فحوص CI مسجّلة على الطلب بعد")
    for c in checks:
        state = (c.get("conclusion") or c.get("state") or "").upper()
        name = c.get("name") or c.get("context") or "؟"
        if state in PASSING:
            continue
        if state in PENDING or not state:
            reasons.append(f"فحص لم يكتمل: {name}")
        else:
            reasons.append(f"فحص غير ناجح ({state}): {name}")
    return (not reasons), reasons, head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pr")
    ap.add_argument("--repo")
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args()
    try:
        ok, reasons, head = evaluate(args.pr, args.repo)
    except (subprocess.CalledProcessError, json.JSONDecodeError, GateError) as exc:
        print(f"[خطأ] {exc}", file=sys.stderr)
        return 2
    if ok:
        print(f"[مسموح] الطلب #{args.pr} يستوفي شروط الدمج الآلي")
        if args.enable:
            # --match-head-commit: التفعيل للرأس المقيس وحده؛ دفعٌ لاحق يُسقطه فلا يُدمج ما لم يُفحص.
            cmd = ["gh", "pr", "merge", args.pr, "--auto", "--squash", "--match-head-commit", head]
            subprocess.run(cmd + (["--repo", args.repo] if args.repo else []), check=True)
            print("[تفعيل] auto-merge مفعّل؛ طابور الدمج يتولّى الباقي")
        return 0
    print(f"[ممنوع] الطلب #{args.pr} يبقى دمجًا يدويًا:")
    for r in reasons:
        print(f"  - {r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
