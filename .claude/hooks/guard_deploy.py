#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): يحجب الدمج والنشر من الجلسة بأي صيغة، لا بالبادئة التي تطابقها قواعد deny.

قواعد deny في settings.json تطابق بداية الأمر، فتلتفّ عليها `gh api …/merge` و`npx @railway/cli`
و`--ena` (مراجعة 2026-11-19، ج1). هذا الحارس يبحث في نص الأمر كله. الدمج والنشر بيد المالك وحده.
الخروج 2 يمنع الأمر ويعرض السبب للنموذج؛ 0 يسمح.
"""

from __future__ import annotations

import json
import re
import sys

_BOUNDARY = r"(?:^|[\s;&|(`'\"])"
_END = r"(?=$|[\s;&|)`'\"])"

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gh-pr-merge", re.compile(r"\bgh(?:\.exe)?\s+pr\s+merge\b", re.I)),
    # REST (pulls/N/merge) وGraphQL (mergePullRequest، enablePullRequestAutoMerge) في استدعاء واحد.
    ("gh-api-merge", re.compile(r"\bgh(?:\.exe)?\s+api\b[^\n;&|]*merge", re.I)),
    ("railway-cli", re.compile(_BOUNDARY + r"(?:[^\s;&|]*[\/])?railway(?:\.exe|\.cmd|\.ps1)?" + _END, re.I)),
    ("railway-npm", re.compile(r"@railway/cli\b", re.I)),
    ("merge-gate-enable", re.compile(r"merge_gate(?:\.py)?\b[^\n;&|]*\s--?en", re.I)),
)

MESSAGE = "guard_deploy: {rule} — الدمج والنشر بيد المالك (CLAUDE.md «ما لا تفعله»)؛ اطلب منه تنفيذه."


def hits(command: str) -> list[str]:
    return [name for name, pattern in RULES if pattern.search(command)]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    found = hits(command)
    if not found:
        return 0
    print(MESSAGE.format(rule=", ".join(found)), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
