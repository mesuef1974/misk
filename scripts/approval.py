"""مصدر واحد لتعبير سطر الاعتماد؛ يستورده merge_gate.py وpr_approval_head_check.py فلا منطق ثانٍ.

الصيغة في وصف الطلب، سطرًا وحده ظاهرًا في الصفحة:
    اعتُمد من المالك — 2026-11-07 — الرأس 1a2b3c4d
الربط بالرأس إلزامي: دفعٌ بعد الاعتماد يُبطل السطر (الفحص يقارن البادئة بالـ SHA الحالي).
"""

from __future__ import annotations

import re

# السطر كله ولا شيء غيره (د4 من مراجعة 2026-11-19 الثانية): لا يُقبل داخل رابط أو وسم أو جملة أطول.
APPROVAL = re.compile(
    r"^[ \t]*اعتُمد من المالك — (?P<date>\d{4}-\d{2}-\d{2}) — الرأس (?P<sha>[0-9a-f]{7,40})[ \t\r]*$",
    re.MULTILINE,
)
MIN_HEAD = 7

# ما لا تعرضه صفحة الطلب سطرًا عاديًّا: تعليق HTML (وغير المغلق يخفي ما بعده)، وكتلة شيفرة مسوّرة
# (وغير المغلقة تمتدّ إلى النهاية)، وسطر مزاح بأربع مسافات أو بجدولة (كتلة شيفرة مزاحة)، وشيفرة سطرية.
# السطر هناك لا يراه المالك قرارًا فلا يُعدّ اعتمادًا.
HIDDEN = re.compile(
    r"<!--.*?(?:-->|\Z)"
    r"|^[ \t]{0,3}(?P<fence>`{3,}|~{3,}).*?(?:^[ \t]{0,3}(?P=fence)[`~]*[ \t\r]*$|\Z)"
    r"|^(?: {4}| {0,3}\t)[^\n]*"
    r"|`[^`\n]*`",
    re.DOTALL | re.MULTILINE,
)

# ز6 من مراجعة 2026-11-20: محررات العربية تُدرج محارف اتجاه لا تُرى، ومسافات لا تنكسر بدل المسافة.
# لا تغيّر ما يراه المالك، فتُحذف الأولى وتصير الثانية مسافة قبل المطابقة.
BIDI_MARKS = re.compile("[؜‎‏‪-‮⁦-⁩﻿]")
NO_BREAK_SPACES = re.compile("[   ]")


def visible_text(body: str) -> str:
    text = NO_BREAK_SPACES.sub(" ", BIDI_MARKS.sub("", body or ""))
    return HIDDEN.sub("\n", text)


def approved_heads(body: str) -> list[str]:
    return [m.group("sha") for m in APPROVAL.finditer(visible_text(body))]


def same_head(written: str, head: str) -> bool:
    written, head = written.lower(), head.lower()
    return (
        len(written) >= MIN_HEAD
        and len(head) >= MIN_HEAD
        and (head.startswith(written) or written.startswith(head))
    )


def approval_line(date: str, sha: str) -> str:
    return f"اعتُمد من المالك — {date} — الرأس {sha[:8]}"
