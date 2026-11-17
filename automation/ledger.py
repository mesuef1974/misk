#!/usr/bin/env python3
"""دفتر البطاقات: أحداث JSONL append-only. ملف لكل بطاقة في automation/ledger/<card_id>.jsonl.

الحالة الحالية = آخر حدث. لا تحرير ولا حذف؛ التصحيح حدث جديد.
"""

from __future__ import annotations

import argparse
import io
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "automation" / "ledger"
STATES = (
    "created",
    "ready",
    "claimed",
    "coded",
    "prepush_ok",
    "prepush_failed",
    "pr_opened",
    "ci_green",
    "approved",
    "merged",
    "deployed",
    "blocked",
    "cancelled",
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def card_path(card_id: str) -> Path:
    return LEDGER / f"{card_id}.jsonl"


def append(card_id: str, event: str, **data) -> dict:
    if event not in STATES:
        raise ValueError(f"حدث غير معروف: {event}")
    LEDGER.mkdir(parents=True, exist_ok=True)
    row = {"card": card_id, "event": event, "at": now(), **data}
    with card_path(card_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def events(card_id: str) -> list[dict]:
    path = card_path(card_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def state(card_id: str) -> dict | None:
    evs = events(card_id)
    return evs[-1] if evs else None


def first(card_id: str) -> dict | None:
    evs = events(card_id)
    return evs[0] if evs else None


def all_cards() -> list[str]:
    if not LEDGER.exists():
        return []
    return sorted(p.stem for p in LEDGER.glob("*.jsonl"))


def cards_in(*wanted: str) -> list[str]:
    return [c for c in all_cards() if (s := state(c)) and s["event"] in wanted]


def new_card(title: str, body: str, success: str = "") -> str:
    card_id = datetime.now(UTC).strftime("%Y%m%d") + "-" + secrets.token_hex(3)
    append(card_id, "created", title=title, body=body, success=success)
    return card_id


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("title")
    p_new.add_argument("--body", required=True, help="ما يجب فعله")
    p_new.add_argument("--success", default="", help="ما يُعدّ نجاحًا (اختبار/سلوك قابل للتحقق)")
    p_ready = sub.add_parser("ready")
    p_ready.add_argument("card")
    p_ev = sub.add_parser("event")
    p_ev.add_argument("card")
    p_ev.add_argument("event", choices=STATES)
    p_ev.add_argument("--note", default="")
    sub.add_parser("list")
    p_show = sub.add_parser("show")
    p_show.add_argument("card")
    args = ap.parse_args(argv)

    if args.cmd == "new":
        cid = new_card(args.title, args.body, args.success)
        print(cid)
    elif args.cmd == "ready":
        append(args.card, "ready")
        print(f"{args.card} → ready")
    elif args.cmd == "event":
        append(args.card, args.event, note=args.note)
        print(f"{args.card} → {args.event}")
    elif args.cmd == "list":
        for c in all_cards():
            s, f = state(c) or {}, first(c) or {}
            print(f"{c}  {s.get('event', ''):<14} {f.get('title', '')}")
    elif args.cmd == "show":
        for e in events(args.card):
            print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
