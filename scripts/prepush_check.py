#!/usr/bin/env python3
"""الفحوص السريعة نفسها التي يشغّلها CI، محليًا قبل الدفع، فيُكتشف الخطأ في ثوانٍ لا بعد دورة CI.

الفحوص: ruff check، ruff format --check، makemigrations --check، تصادم أرقام الهجرات (إن وُجد gh)،
detect-secrets على ما تغيّر، pytest سريع (-x -q)، وبناء الواجهة اختياريًا (--frontend).

الاستعمال:  python scripts/prepush_check.py [--base origin/main] [--frontend] [--allow-missing]
الخروج:     0 كل ما قيس نجح، 1 فحص فشل، 3 أداة غائبة بلا --allow-missing (لا نجاح صامت).
يكتب بصمة النجاح في .prepush_receipt (HEAD + الوقت) ليقرأها runner.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK, FAIL, MISSING = "ok", "fail", "missing"
TEST_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.testing",
    "SECRET_KEY": "ci-testing-only",  # pragma: allowlist secret
}


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, **(env or {})},
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]} غير مثبَّت")


def tail(proc: subprocess.CompletedProcess, lines: int = 12) -> str:
    text = (proc.stdout or "") + (proc.stderr or "")
    return "\n".join(text.strip().splitlines()[-lines:])


def status(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    if proc.returncode == 127:
        return MISSING, tail(proc)
    return (OK if proc.returncode == 0 else FAIL), tail(proc)


def changed_files(base: str) -> list[str]:
    mb = run(["git", "merge-base", "HEAD", base])
    if mb.returncode != 0:
        return []
    diff = run(["git", "diff", "--name-only", mb.stdout.strip(), "HEAD"])
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"])
    staged = run(["git", "diff", "--name-only", "--cached"])
    files = set(diff.stdout.split()) | set(untracked.stdout.split()) | set(staged.stdout.split())
    return sorted(f for f in files if (ROOT / f).is_file())


def check_ruff() -> tuple[str, str]:
    return status(run([sys.executable, "-m", "ruff", "check", "."]))


def check_format() -> tuple[str, str]:
    return status(run([sys.executable, "-m", "ruff", "format", "--check", "."]))


def check_migrations() -> tuple[str, str]:
    return status(run([sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], env=TEST_ENV))


def check_collisions(base: str) -> tuple[str, str]:
    if not shutil.which("gh"):
        return MISSING, "gh غير مثبَّت"
    proc = run([sys.executable, "scripts/check_migration_collisions.py", "--base", base])
    if proc.returncode == 3:
        return MISSING, tail(proc)
    return status(proc)


def check_secrets(files: list[str]) -> tuple[str, str]:
    if not files:
        return OK, "لا ملفات متغيرة"
    cmd = [sys.executable, "-m", "detect_secrets", "scan", *files]
    proc = run(cmd)
    if proc.returncode == 127 or "No module named" in (proc.stderr or ""):
        return MISSING, "detect-secrets غير مثبَّت"
    try:
        results = json.loads(proc.stdout or "{}").get("results", {})
    except json.JSONDecodeError:
        return FAIL, tail(proc)
    if results:
        return FAIL, "أسرار محتملة في: " + ", ".join(sorted(results))
    return OK, f"{len(files)} ملفًا بلا أسرار"


def check_tests() -> tuple[str, str]:
    return status(
        run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
            env=TEST_ENV,
        )
    )


def check_frontend() -> tuple[str, str]:
    fe = ROOT / "frontend"
    if not (fe / "node_modules").exists():
        return MISSING, "frontend/node_modules غائب (npm ci)"
    npm = shutil.which("npm") or "npm"
    for script in ("typecheck", "test"):
        proc = run([npm, "run", script, "--silent"], cwd=fe)
        if proc.returncode != 0:
            return FAIL, f"npm run {script}:\n{tail(proc)}"
    return OK, "typecheck + vitest"


def write_receipt(results: dict[str, tuple[str, str]]) -> None:
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    (ROOT / ".prepush_receipt").write_text(
        json.dumps(
            {"head": head, "at": int(time.time()), "checks": {k: v[0] for k, v in results.items()}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--frontend", action="store_true")
    ap.add_argument("--allow-missing", action="store_true")
    ap.add_argument("--skip", default="", help="فحوص تُترك، مفصولة بفاصلة")
    args = ap.parse_args(argv)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    checks = {
        "ruff": check_ruff,
        "format": check_format,
        "migrations": check_migrations,
        "collisions": lambda: check_collisions(args.base),
        "secrets": lambda: check_secrets(changed_files(args.base)),
        "tests": check_tests,
    }
    if args.frontend:
        checks["frontend"] = check_frontend

    results: dict[str, tuple[str, str]] = {}
    for name, fn in checks.items():
        if name in skip:
            continue
        started = time.time()
        results[name] = fn()
        mark = {OK: "✔", FAIL: "✘", MISSING: "∅"}[results[name][0]]
        print(f"{mark} {name:<11} {time.time() - started:5.1f}s")
        if results[name][0] != OK and results[name][1]:
            print("   " + results[name][1].replace("\n", "\n   "))

    failed = [k for k, v in results.items() if v[0] == FAIL]
    missing = [k for k, v in results.items() if v[0] == MISSING]
    if failed:
        print(f"\nفشل: {', '.join(failed)}")
        return 1
    if missing and not args.allow_missing:
        print(f"\nغير مقيس (أداة غائبة): {', '.join(missing)} — ثبّتها أو مرّر --allow-missing")
        return 3
    write_receipt(results)
    print("\nكل ما قيس نجح — .prepush_receipt مكتوب")
    return 0


if __name__ == "__main__":
    sys.exit(main())
