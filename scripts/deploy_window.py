"""نافذة النشر: كل دمج إلى main نشر فوري على Railway، فلا دمج وقت الدوام إلا الإصلاح العاجل.

يُفرض في طابور الدمج (merge_group) وحده. الإصلاح العاجل يمرّ بوسم LABEL على الطلب.
الإعداد من القالب: الإزاحة 3 ساعة، الأيام weekday() = 6,0,1,2,3، الساعات 07-14.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=int("3")))
WORK_DAYS = {int(d) for d in "6,0,1,2,3".split(",")}
_HOURS = "07-14".split("-")
WINDOW_START_HOUR, WINDOW_END_HOUR = int(_HOURS[0]), int(_HOURS[1])
LABEL = "نشر-عاجل"
_QUEUE_PR_RE = re.compile(r"/pr-(\d+)-")


def in_work_hours(now: datetime) -> bool:
    local = now.astimezone(LOCAL_TZ)
    return local.weekday() in WORK_DAYS and WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR


def queued_pr_number(head_ref: str) -> int | None:
    m = _QUEUE_PR_RE.search(head_ref)
    return int(m.group(1)) if m else None


def pr_labels(repo: str, number: int) -> list[str]:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{number}", "--jq", "[.labels[].name]"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def decide(event: str, now: datetime, labels: list[str] | None) -> tuple[bool, str]:
    local = now.astimezone(LOCAL_TZ).strftime("%A %H:%M")
    end = f"{WINDOW_END_HOUR}:00"
    if not in_work_hours(now):
        return True, f"خارج الدوام ({local}) — النشر مسموح."
    if event != "merge_group":
        return True, f"وقت الدوام ({local}) — لا منع هنا؛ طابور الدمج سيرفض حتى {end} ما لم يُوسم «{LABEL}»."
    if labels and LABEL in labels:
        return True, f"وقت الدوام ({local}) لكن الطلب موسوم «{LABEL}» — يمرّ إصلاحًا عاجلًا."
    return False, f"وقت الدوام ({local}): الدمج نشر فوري وممنوع الآن. أعد بعد {end} أو وسم الطلب «{LABEL}»."


def main() -> int:
    event = os.environ.get("EVENT", "")
    now = datetime.now(UTC)
    labels = None
    if event == "merge_group" and in_work_hours(now):
        number = queued_pr_number(os.environ.get("HEAD_REF", ""))
        if number is not None:
            labels = pr_labels(os.environ["REPO"], number)
    allowed, message = decide(event, now, labels)
    print(message if allowed else f"::error::{message}")
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
