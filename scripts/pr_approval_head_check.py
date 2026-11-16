#!/usr/bin/env python3
"""فحص CI: سطر الاعتماد في وصف الطلب يطابق رأسه الحالي. دفعٌ بعد الاعتماد يُسقط الطلب.

يُعاد عند edited فيمرّ متى كُتب سطر على الرأس الجديد. المؤلّف الآلي ([bot]) مستثنى.
    python scripts/pr_approval_head_check.py <رقم الطلب> [--repo owner/name]
الخروج: 0 ناجح/مستثنى، 1 فشل، 2 خطأ قراءة.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import approved_heads, same_head  # noqa: E402


def is_bot(author: str) -> bool:
    return author.startswith("app/") or author.endswith("[bot]")


def verdict(body: str, head: str, author: str = "") -> tuple[str, str]:
    if is_bot(author):
        return "exempt", f"مؤلّف آلي ({author})"
    heads = approved_heads(body)
    if not heads:
        return "no_line", "لا سطر اعتماد في وصف الطلب"
    if any(same_head(h, head) for h in heads):
        return "ok", "سطر الاعتماد يطابق الرأس"
    return "stale_head", f"سطر الاعتماد على رأس قديم ({', '.join(h[:8] for h in heads)})، الحالي {head[:8]}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("number")
    ap.add_argument("--repo")
    args = ap.parse_args(argv)
    cmd = ["gh", "pr", "view", args.number, "--json", "body,headRefOid,author"] + (
        ["--repo", args.repo] if args.repo else []
    )
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(f"تعذّرت قراءة الطلب: {proc.stderr.strip()[:200]}", file=sys.stderr)
        return 2
    data = json.loads(proc.stdout)
    state, message = verdict(
        data.get("body") or "", data.get("headRefOid") or "", (data.get("author") or {}).get("login", "")
    )
    ok = state in ("ok", "exempt")
    print(f"{'✔' if ok else '✘'} {state}: {message}")
    if not ok:
        print(
            "::error::اكتب في وصف الطلب: اعتُمد من المالك — <التاريخ> — الرأس <sha8> (بعد مراجعة هذا الرأس تحديدًا)",
            file=sys.stderr,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
