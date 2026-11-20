#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): يحجب الدمج والنشر من الجلسة بأي صيغة، لا بالبادئة التي تطابقها قواعد deny.

قواعد deny في settings.json تطابق بداية الأمر، فتلتفّ عليها `gh api …/merge` و`npx @railway/cli`
و`--ena` (مراجعة 2026-11-19، ج1). هذا الحارس يبحث في نص الأمر كله. الدمج والنشر بيد المالك وحده.
الخروج 2 يمنع الأمر ويعرض السبب للنموذج؛ 0 يسمح.

د1 (المراجعة الثانية): مطابقة النص لا تحيط بكل صيغة ما دامت الجلسة تملك رموز gh وrailway، فالحارس
يحجب أيضًا الوسائل التي تخفي الأمر عن المطابقة: الأسماء المستعارة، وGraphQL، ومسار gh api المبني
بمتغيّر أو من ملف، والكلمات المركَّبة من متغيّر أو أقواس، وشيفرة المفسّرات التي تذكر gh أو railway.
هذا تخفيف؛ الإصلاح الجذري خارج المستودع (هوية GitHub بلا صلاحية دمج، وruleset، ولا رمز Railway).
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
    # الاسم المستعار يُحفظ في إعداد gh فيبقى للجلسات التالية، ثم يُستدعى باسم لا يطابقه شيء.
    ("gh-alias", re.compile(r"\bgh(?:\.exe)?\s+alias\b", re.I)),
    # الاستعلام قد يأتي من ملف (`-F query=@q.graphql`) فلا يُرى نصّه هنا.
    ("gh-api-graphql", re.compile(r"\bgh(?:\.exe)?\s+api\s+graphql\b", re.I)),
    # مسار أو جسم لا يُرى نصّه: توسيع متغيّر أو أمر، أو قراءة من ملف.
    ("gh-api-indirect", re.compile(r"\bgh(?:\.exe)?\s+api\b[^\n;&|]*(?:\$|`|--input\b|=@)", re.I)),
    # كلمة تُركَّب من توسيع ملتصق بحروف (`${r}way`، `$(echo rail)way`) أو من قوسين فارغين (`rail''way`).
    (
        "glued-expansion",
        re.compile(
            r"\$\{\w+\}[A-Za-z]|[A-Za-z]\$\{\w+\}|\$\([^)]*\)[A-Za-z]|[A-Za-z]\$\(|[A-Za-z](?:''|\"\")[A-Za-z]"
        ),
    ),
)

# شيفرة تُمرَّر إلى مفسّر (`-c`، `-e`، `-Command`، أو stdin بـ`-`) أو إلى eval/iex: تستطيع بناء أي أمر.
_INTERPRETER = re.compile(
    r"(?:^|[\s;&|(`])(?:python3?|py|node|deno|bun|ruby|perl|php|bash|sh|zsh|dash|pwsh|powershell)(?:\.exe)?"
    r"\s+(?:[^\n;&|]*\s)?(?:-c|-e|--eval|-Command|-EncodedCommand|-enc|-)(?=$|\s|[\"'])"
    r"|(?:^|[\s;&|(`])(?:eval|iex|Invoke-Expression)\b",
    re.I,
)
_DEPLOY_WORDS = re.compile(r"\bgh\b|rail|api\.github\.com|graphql", re.I)

MESSAGE = "guard_deploy: {rule} — الدمج والنشر بيد المالك (CLAUDE.md «ما لا تفعله»)؛ اطلب منه تنفيذه."


def hits(command: str) -> list[str]:
    found = [name for name, pattern in RULES if pattern.search(command)]
    if _INTERPRETER.search(command) and _DEPLOY_WORDS.search(command):
        found.append("inline-interpreter")
    return found


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
