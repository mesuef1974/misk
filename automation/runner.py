#!/usr/bin/env python3
"""المشغّل المجدوَل: بطاقة ready → worktree → claude بصلاحيات مخفَّضة → فحص محلي → PR. كل خطوة حدث في الدفتر.

الصلاحيات: النموذج يكتب الشيفرة ويشغّل الاختبارات فقط. الدفع وفتح الطلب يفعلهما هذا السكربت بعد نجاح
prepush_check.py، والدمج بوابة CI وطابور الدمج. حارس .claude/hooks/guard_git.py يحجب ما يتسرّب.

    python automation/runner.py --once [--dry-run] [--max-turns 40] [--model <id>]
يُجدوَل كل N دقائق؛ قفل automation/.lock يمنع تشغيلين متوازيين.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

ROOT = ledger.ROOT
WORKTREES = ROOT / ".worktrees"
LOCK = ROOT / "automation" / ".lock"
LOCK_STALE_SECONDS = 3 * 60 * 60

DISALLOWED_TOOLS = [
    "Bash(git push*)",
    "Bash(git merge*)",
    "Bash(git rebase*)",
    "Bash(gh pr merge*)",
    "Bash(gh pr create*)",
    "Bash(railway*)",
    "Bash(rm -rf*)",
    "WebFetch",
]

PROMPT = """أنت تنفّذ بطاقة عمل واحدة في مستودع Django + Vue. اعمل داخل هذا المجلد فقط.

العنوان: {title}
المطلوب:
{body}

ما يُعدّ نجاحًا (يجب أن يتحقق باختبار أو سلوك قابل للتشغيل):
{success}

القواعد:
- لا تعدّل ملفات .github/ أو scripts/ أو security/ أو lockfiles أو requirements*.txt أو Dockerfile أو railway.toml.
- كل تغيير في النماذج يرافقه makemigrations، وكل منطق في services.py لا في النماذج أو العروض.
- أضف اختبارًا يفشل قبل تغييرك وينجح بعده.
- في النهاية شغّل: python scripts/prepush_check.py --allow-missing، وأصلح ما يفشل.
- أودع تغييراتك بـ git add <مسارات صريحة> ثم git commit برسالة عربية واضحة. لا تدفع.
"""


def sh(cmd: list[str], cwd: Path = ROOT, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace", check=check, **kw)


def acquire_lock() -> bool:
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < LOCK_STALE_SECONDS:
            print(f"مشغّل آخر يعمل (قفل عمره {int(age)} ث) — خروج")
            return False
        print("قفل قديم — يُزال")
        LOCK.unlink()
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    LOCK.unlink(missing_ok=True)


def pick_card() -> str | None:
    ready = ledger.cards_in("ready")
    return ready[0] if ready else None


def make_worktree(card: str) -> tuple[Path, str]:
    WORKTREES.mkdir(exist_ok=True)
    branch = f"card/{card}"
    path = WORKTREES / card
    sh(["git", "fetch", "origin", "main"], check=False)
    if path.exists():
        return path, branch
    sh(["git", "worktree", "add", "-b", branch, str(path), "origin/main"])
    return path, branch


def run_model(path: Path, card: str, model: str | None, max_turns: int) -> int:
    meta = ledger.first(card) or {}
    prompt = PROMPT.format(
        title=meta.get("title", card),
        body=meta.get("body", ""),
        success=meta.get("success", "غير محدد — حدّده أولًا في الاختبار"),
    )
    claude = shutil.which("claude") or "claude"
    cmd = [
        claude,
        "-p",
        prompt,
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "acceptEdits",
        "--disallowedTools",
        *DISALLOWED_TOOLS,
    ]
    if model:
        cmd += ["--model", model]
    proc = sh(cmd, cwd=path, check=False)
    return proc.returncode


def prepush(path: Path) -> bool:
    proc = sh([sys.executable, "scripts/prepush_check.py", "--allow-missing"], cwd=path, check=False)
    return proc.returncode == 0


def push_and_open_pr(path: Path, branch: str, card: str) -> str:
    sh(["git", "push", "-u", "origin", branch], cwd=path)
    meta = ledger.first(card) or {}
    body = f"بطاقة `{card}`\n\n{meta.get('body', '')}\n\nالنجاح: {meta.get('success', '')}\n\n(يُكتب سطر الاعتماد هنا بعد المراجعة: اعتُمد من المالك — YYYY-MM-DD — الرأس sha8)"
    proc = sh(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            meta.get("title", card),
            "--body",
            body,
        ],
        cwd=path,
        capture_output=True,
    )
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--max-turns", type=int, default=40)
    args = ap.parse_args(argv)

    card = pick_card()
    if not card:
        print("لا بطاقات ready")
        return 0
    if args.dry_run:
        print(f"سيُلتقط: {card} → worktree .worktrees/{card} → claude → prepush → PR")
        return 0
    if not acquire_lock():
        return 0
    try:
        ledger.append(card, "claimed", pid=os.getpid())
        path, branch = make_worktree(card)
        rc = run_model(path, card, args.model, args.max_turns)
        head = sh(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True).stdout.strip()
        ledger.append(card, "coded", exit_code=rc, head=head)
        if not prepush(path):
            ledger.append(card, "prepush_failed", head=head)
            print("الفحص المحلي فشل — البطاقة تبقى في worktree للمراجعة")
            return 1
        ledger.append(card, "prepush_ok", head=head)
        url = push_and_open_pr(path, branch, card)
        ledger.append(card, "pr_opened", url=url, head=head)
        print(f"PR: {url}")
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
