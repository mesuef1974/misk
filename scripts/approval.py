"""مصدر واحد لتعبير سطر الاعتماد؛ يستورده merge_gate.py وpr_approval_head_check.py فلا منطق ثانٍ.

الصيغة في وصف الطلب:
    اعتُمد من المالك — 2026-11-07 — الرأس 1a2b3c4d
الربط بالرأس إلزامي: دفعٌ بعد الاعتماد يُبطل السطر (الفحص يقارن البادئة بالـ SHA الحالي).
"""

from __future__ import annotations

import re

APPROVAL = re.compile(r"اعتُمد من المالك — (?P<date>\d{4}-\d{2}-\d{2}) — الرأس (?P<sha>[0-9a-f]{7,40})")
MIN_HEAD = 7


def approved_heads(body: str) -> list[str]:
    return [m.group("sha") for m in APPROVAL.finditer(body or "")]


def same_head(written: str, head: str) -> bool:
    written, head = written.lower(), head.lower()
    return (
        len(written) >= MIN_HEAD
        and len(head) >= MIN_HEAD
        and (head.startswith(written) or written.startswith(head))
    )


def approval_line(date: str, sha: str) -> str:
    return f"اعتُمد من المالك — {date} — الرأس {sha[:8]}"
