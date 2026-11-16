#!/usr/bin/env python3
"""حارس تصادم أرقام الهجرات بين الطلبات المفتوحة وما دخل main بعد الأساس.

worktree لكل بطاقة يعني فرعين قد يضيفان 0007_x.py في التطبيق نفسه ولا يظهر التصادم إلا عند الدمج.
    python scripts/check_migration_collisions.py [--base origin/main]
الخروج: 0 لا تصادم، 1 تصادم، 3 غير مقيس (gh/git/شبكة غائبة) — لا نجاح صامت.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

MIGRATION_RE = re.compile(r"^(?P<app>[\w./-]+?)/migrations/(?P<num>\d{4})_[\w]+\.py$")
OK, COLLISION, MISSING = 0, 1, 3


class NotMeasuredError(Exception):
    pass


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError as exc:
        raise NotMeasuredError(f"{cmd[0]} غير مثبَّت") from exc


def migration_keys(paths: list[str]) -> dict[tuple[str, str], str]:
    keys: dict[tuple[str, str], str] = {}
    for path in paths:
        m = MIGRATION_RE.match(path)
        if m:
            keys[(m["app"], m["num"])] = path
    return keys


def find_collisions(mine: list[str], others: dict[str, list[str]]) -> list[tuple[str, str, str, str, str]]:
    own = migration_keys(mine)
    found = []
    for label, paths in others.items():
        for key, other_path in migration_keys(paths).items():
            own_path = own.get(key)
            if own_path and own_path != other_path:
                found.append((key[0], key[1], label, own_path, other_path))
    return found


def branch_added_paths(base: str) -> tuple[list[str], str]:
    mb = run(["git", "merge-base", "HEAD", base])
    if mb.returncode != 0 or not mb.stdout.strip():
        raise NotMeasuredError(f"تعذّر merge-base مع {base}")
    sha = mb.stdout.strip()
    committed = run(["git", "diff", "--name-only", "--diff-filter=A", sha, "HEAD"])
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"])
    return sorted(set(committed.stdout.splitlines()) | set(untracked.stdout.splitlines())), sha


def gh_json(args: list[str]):
    proc = run(["gh", *args])
    if proc.returncode != 0:
        raise NotMeasuredError(f"gh فشل: {(proc.stderr or '').strip()[:120]}")
    try:
        return json.loads(proc.stdout or "null")
    except ValueError as exc:
        raise NotMeasuredError("ردّ gh ليس JSON") from exc


def open_prs() -> dict[str, dict]:
    prs = gh_json(
        ["pr", "list", "--state", "open", "--limit", "200", "--json", "number,headRefName,headRefOid"]
    )
    result = {}
    for pr in prs or []:
        # placeholders الخاصة بـ gh تُبنى بالتسلسل حتى لا يفسّرها Jinja عند توليد القالب.
        owner_repo = "{" + "owner" + "}/{" + "repo" + "}"
        pages = gh_json(["api", f"repos/{owner_repo}/pulls/{pr['number']}/files", "--paginate", "--slurp"])
        added = [f["filename"] for page in pages or [] for f in page if f.get("status") == "added"]
        result[f"#{pr['number']} ({pr['headRefName']})"] = {
            "head": pr["headRefOid"],
            "branch": pr["headRefName"],
            "files": added,
        }
    return result


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args(argv)
    try:
        mine, mb = branch_added_paths(args.base)
        if not migration_keys(mine):
            print("لا هجرة مضافة في الفرع — لا تصادم ممكن")
            return OK
        branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        others = {
            label: info["files"]
            for label, info in open_prs().items()
            if not (info["head"] == head or info["branch"] == branch)
        }
        others[f"{args.base} بعد الأساس"] = run(
            ["git", "diff", "--name-only", "--diff-filter=A", mb, args.base]
        ).stdout.splitlines()
    except NotMeasuredError as exc:
        print(f"غير مقيس: {exc}")
        return MISSING
    collisions = find_collisions(mine, others)
    if not collisions:
        print(f"لا تصادم مع {len(others) - 1} طلبًا مفتوحًا ولا مع main")
        return OK
    for app, num, label, own, theirs in collisions:
        print(f"تصادم: {app} رقم {num} مع {label}: ملفّك {own} وملفّه {theirs}")
    return COLLISION


if __name__ == "__main__":
    sys.exit(main())
