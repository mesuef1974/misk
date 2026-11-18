"""نافذة النشر: كل دمج إلى main نشر فوري على Railway، فلا دمج وقت الدوام إلا الإصلاح العاجل.

يُفرض على الطلب نفسه (pull_request) وفي طابور الدمج (merge_group)؛ فحص «بوابة الجودة» المطلوب يتبعه.
الإصلاح العاجل يمرّ بوسم LABEL على الطلب. الفحص يُحسب وقت تشغيله، فيعيده `refresh` المجدوَل عند
حدَّي النافذة على كل طلب مفتوح تغيّر حكمه.
    python scripts/deploy_window.py            # فحص الطلب الحالي من متغيرات البيئة
    python scripts/deploy_window.py refresh    # إعادة تشغيل الفحص حيث تغيّر الحكم
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
ENFORCED_EVENTS = ("pull_request", "merge_group")
WORKFLOW_FILE = "quality-gate.yml"
JOB_NAME = "نافذة النشر"
_QUEUE_PR_RE = re.compile(r"/pr-(\d+)-")


def in_work_hours(now: datetime) -> bool:
    local = now.astimezone(LOCAL_TZ)
    return local.weekday() in WORK_DAYS and WINDOW_START_HOUR <= local.hour < WINDOW_END_HOUR


def queued_pr_number(head_ref: str) -> int | None:
    m = _QUEUE_PR_RE.search(head_ref)
    return int(m.group(1)) if m else None


def pr_number(event: str, env: dict[str, str]) -> int | None:
    if event == "pull_request":
        raw = env.get("PR_NUMBER", "")
        return int(raw) if raw.isdigit() else None
    return queued_pr_number(env.get("HEAD_REF", ""))


def _gh_json(*args: str):
    out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


def pr_labels(repo: str, number: int) -> list[str]:
    return _gh_json(f"repos/{repo}/pulls/{number}", "--jq", "[.labels[].name]")


def decide(event: str, now: datetime, labels: list[str] | None) -> tuple[bool, str]:
    local = now.astimezone(LOCAL_TZ).strftime("%A %H:%M")
    end = f"{WINDOW_END_HOUR}:00"
    if not in_work_hours(now):
        return True, f"خارج الدوام ({local}) — النشر مسموح."
    if event not in ENFORCED_EVENTS:
        return (
            True,
            f"وقت الدوام ({local}) — لا منع في حدث «{event}»؛ الطلب نفسه يُرفض حتى {end} ما لم يُوسم «{LABEL}».",
        )
    if labels and LABEL in labels:
        return True, f"وقت الدوام ({local}) لكن الطلب موسوم «{LABEL}» — يمرّ إصلاحًا عاجلًا."
    return False, f"وقت الدوام ({local}): الدمج نشر فوري وممنوع الآن. أعد بعد {end} أو وسم الطلب «{LABEL}»."


def needs_rerun(conclusion: str | None, allowed: bool) -> bool:
    """يُعاد الفحص المكتمل الذي خالف حكمُه الحكمَ الآن؛ الجاري والملغى والمتخطّى يُتركان."""
    if conclusion == "success":
        return not allowed
    if conclusion == "failure":
        return allowed
    return False


def window_job(repo: str, head_sha: str) -> dict | None:
    runs = _gh_json(
        f"repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs?head_sha={head_sha}&event=pull_request&per_page=1",
        "--jq",
        ".workflow_runs",
    )
    if not runs:
        return None
    jobs = _gh_json(
        f"repos/{repo}/actions/runs/{runs[0]['id']}/jobs?filter=latest&per_page=100", "--jq", ".jobs"
    )
    return next((j for j in jobs if j["name"] == JOB_NAME), None)


def refresh(repo: str, now: datetime) -> int:
    """يعيد تشغيل فحص النافذة على كل طلب مفتوح إلى main تغيّر حكمه. الخروج 1 إن فشلت إعادةٌ."""
    prs = _gh_json(
        f"repos/{repo}/pulls?state=open&base=main&per_page=100",
        "--jq",
        "[.[] | {number, sha: .head.sha, labels: [.labels[].name]}]",
    )
    failed = 0
    for pr in prs:
        allowed, _ = decide("pull_request", now, pr["labels"])
        job = window_job(repo, pr["sha"])
        if job is None or not needs_rerun(job.get("conclusion"), allowed):
            continue
        done = subprocess.run(
            ["gh", "api", "-X", "POST", f"repos/{repo}/actions/jobs/{job['id']}/rerun"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        ok = done.returncode == 0
        failed += 0 if ok else 1
        print(
            f"{'✔' if ok else '✘'} الطلب {pr['number']}: إعادة الفحص ليصير {'مسموحًا' if allowed else 'ممنوعًا'}"
        )
        if not ok:
            print(f"::error::{done.stderr.strip()[:200]}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    now = datetime.now(UTC)
    if args[:1] == ["refresh"]:
        return refresh(os.environ["REPO"], now)
    event = os.environ.get("EVENT", "")
    labels = None
    if event in ENFORCED_EVENTS and in_work_hours(now):
        number = pr_number(event, dict(os.environ))
        if number is not None:
            labels = pr_labels(os.environ["REPO"], number)
    allowed, message = decide(event, now, labels)
    print(message if allowed else f"::error::{message}")
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
