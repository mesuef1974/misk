#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): يحجب الدمج والنشر من الجلسة بأي صيغة، لا بالبادئة التي تطابقها قواعد deny.

قواعد deny في settings.json تطابق بداية الأمر، فتلتفّ عليها `gh api …/merge` و`npx @railway/cli`
و`--ena` (مراجعة 2026-11-19، ج1). هذا الحارس يبحث في نص الأمر كله. الدمج والنشر بيد المالك وحده.
الخروج 2 يمنع الأمر ويعرض السبب للنموذج؛ 0 يسمح.

د1 (المراجعة الثانية): مطابقة النص لا تحيط بكل صيغة ما دامت الجلسة تملك رموز gh وrailway، فالحارس
يحجب أيضًا الوسائل التي تخفي الأمر عن المطابقة: الأسماء المستعارة، وGraphQL، ومسار gh api المبني
بمتغيّر أو من ملف، والكلمات المركَّبة من متغيّر أو أقواس، وشيفرة المفسّرات التي تذكر gh أو railway.
هذا تخفيف؛ الإصلاح الجذري خارج المستودع (هوية GitHub بلا صلاحية دمج، وruleset، ولا رمز Railway).

ز1 (مراجعة 2026-11-20): القواعد تُطابَق على النص كما هو وعلى نسخة مطبَّعة بلا تنصيص ولا شرطة عكسية
(`gh pr "merge"`، `mer\\ge`، `me"rg"e`)، وتقبل أعلامًا عامة بين gh والأمر الفرعي (`gh -R o/r pr merge`).
وقراءة الرمز نفسه محجوبة (`gh auth token`، `git credential fill`): من يملكه يدمج بـcurl. وشيفرة المفسّر
تُحجب إن ذكرت gh أو railway أو استدعت عملية فرعية (`'g'+'h'` لا يذكر gh).
ز5: الكلمة المركَّبة تُحجب في موضع الأمر (`${r}way up`) أو مع كلمة نشر في الأمر نفسه، لا في كل وسيط
(`cp ${f}.txt ${f}bak`). ومسارات ملفات المستودع التي فيها rail لا تُعدّ كلمة نشر، ونص heredoc حرفي
(`<<'EOF'`) يُكتب بـcat أو tee إلى ملف بيانات لا أمر.

دمج بتأكيد المالك (قراره 2026-11-21): صيغة واحدة تمرّ، والأمر كله هي ولا شيء معها:
`gh pr merge <رقم> --squash --match-head-commit <SHA كاملًا>`. الحارس لا يسمح بها بل يحيلها إلى نافذة
الموافقة في التطبيق (`permissionDecision: ask`) مهما كان وضع الأذونات، فلا دمج بلا نقرة المالك.
الربط بالرأس إلزامي: ما يُدمج هو الإيداع الذي اعتُمد، لا ما دُفع بعده. كل صيغة أخرى للدمج تبقى محجوبة.
"""

from __future__ import annotations

import json
import re
import sys

_BOUNDARY = r"(?:^|[\s;&|(`'\"])"
_END = r"(?=$|[\s;&|)`'\"])"
# gh وأعلامه العامة (`-R o/r`، `--repo o/r`، `--repo=o/r`) قبل الأمر الفرعي.
_GH = r"\bgh(?:\.exe)?(?:\s+-[^\s;&|]+(?:\s+[^\s;&|-][^\s;&|]*)?)*\s+"

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gh-pr-merge", re.compile(_GH + r"pr\s+merge\b", re.I)),
    # REST (pulls/N/merge) وGraphQL (mergePullRequest، enablePullRequestAutoMerge) في استدعاء واحد.
    ("gh-api-merge", re.compile(_GH + r"api\b[^\n;&|]*merge", re.I)),
    ("railway-cli", re.compile(_BOUNDARY + r"(?:[^\s;&|]*[\/])?railway(?:\.exe|\.cmd|\.ps1)?" + _END, re.I)),
    ("railway-npm", re.compile(r"@railway/cli\b", re.I)),
    ("merge-gate-enable", re.compile(r"merge_gate(?:\.py)?\b[^\n;&|]*\s--?en", re.I)),
    # الاسم المستعار يُحفظ في إعداد gh فيبقى للجلسات التالية، ثم يُستدعى باسم لا يطابقه شيء.
    ("gh-alias", re.compile(_GH + r"alias\b", re.I)),
    # الاستعلام قد يأتي من ملف (`-F query=@q.graphql`) فلا يُرى نصّه هنا.
    ("gh-api-graphql", re.compile(_GH + r"api\b[^\n;&|]*\bgraphql\b", re.I)),
    # مسار أو جسم لا يُرى نصّه: توسيع متغيّر أو أمر، أو قراءة من ملف.
    ("gh-api-indirect", re.compile(_GH + r"api\b[^\n;&|]*(?:\$|`|--input\b|=@)", re.I)),
    # الرمز نفسه يدمج بأي عميل HTTP: gh يطبعه، وgit يعطيه من مساعد الاعتماد.
    (
        "token-read",
        re.compile(
            _GH + r"auth\s+(?:token\b|git-credential\b|status\b[^\n;&|]*(?:--show-token|\s-t\b))"
            r"|\bgit\b[^\n;&|]*\bcredential\s+fill\b|\bgit-credential-[\w-]+(?:\.exe)?\s+get\b",
            re.I,
        ),
    ),
)

# كلمة تُركَّب من توسيع ملتصق بحروف (`${r}way`، `$(echo rail)way`، `"$r"way`، `rail$w`) أو من قوسين فارغين.
_GLUE = (
    r"\$\{\w+\}[\"']?[A-Za-z]|\$\w+[\"'][A-Za-z]|\$\([^)]*\)[\"']?[A-Za-z]"
    r"|[A-Za-z][\"']?\$[{(\w]|[A-Za-z](?:''|\"\")[A-Za-z]"
)
# موضع الأمر: بداية مقطع، بعد إسنادات المتغيرات والكلمات التي تسبق الأمر.
_GLUE_AT_COMMAND = re.compile(
    r"(?:^|[;&|\n`(]|\$\()\s*(?:(?:\w+=[^\s;&|]*|do|then|else|time|!|exec|command|env|sudo|nohup)\s+)*"
    r"[^\s;&|]*?(?:" + _GLUE + ")"
)
_GLUE_ANYWHERE = re.compile(_GLUE)

# شيفرة تُمرَّر إلى مفسّر (`-c`، `-e`، `-Command`، أو stdin بـ`-`) أو إلى eval/iex: تستطيع بناء أي أمر.
_INTERPRETER = re.compile(
    r"(?:^|[\s;&|(`])(?:python3?|py|node|deno|bun|ruby|perl|php|bash|sh|zsh|dash|pwsh|powershell)(?:\.exe)?"
    r"\s+(?:[^\n;&|]*\s)?(?:-c|-e|--eval|-Command|-EncodedCommand|-enc|-)(?=$|\s|[\"'])"
    r"|(?:^|[\s;&|(`])(?:eval|iex|Invoke-Expression)\b",
    re.I,
)
_DEPLOY_WORDS = re.compile(r"\bgh\b|rail|api\.github\.com|graphql", re.I)
# ما يشغّل عملية فرعية من شيفرة المفسّر: يبني اسم الأمر بالجمع فلا تظهر كلمة نشر.
_SPAWN = re.compile(
    r"child_process|subprocess|\bos\.(?:system|popen|exec\w*|spawn\w*)|\bPopen\b|\bexecSync\b|\bspawnSync\b"
    r"|\bexecFile|Deno\.Command|Bun\.spawn|Start-Process|\bshell_exec\b|\bproc_open\b",
    re.I,
)
# ملفات المستودع التي يحمل اسمها rail: قراءتها أو تشغيلها ليس نشرًا (railway-cli يلتقط الأداة نفسها).
_KNOWN_PATHS = re.compile(
    r"scripts/railway-[\w-]+\.sh|\.railway/[\w./-]*|node_modules/railway/[\w./-]*", re.I
)
# heredoc حرفي (المحدِّد منصَّص فلا توسيع داخله) يُكتب بـcat أو tee بلا أنبوب: النص بيانات لا أمر.
_DATA_HEREDOC = re.compile(
    r"(\b(?:cat|tee)\b[^\n|]*<<-?\s*(['\"])(\w+)\2[^\n|]*)\n.*?\n[ \t]*\3[ \t]*(?=\n|$)", re.S
)

MESSAGE = (
    "guard_deploy: {rule} — النشر بيد المالك، والدمج بصيغة واحدة يوافق عليها في التطبيق: "
    "gh pr merge <رقم> --squash --match-head-commit <SHA كاملًا> (CLAUDE.md «ما لا تفعله»)."
)

# الأمر كله (fullmatch): لا علم آخر (`--admin`، `--auto`، `-R`)، ولا أمر ثانٍ في السطر، ولا تنصيص ولا توسيع.
OWNER_MERGE = re.compile(r"gh pr merge (?P<pr>[1-9]\d{0,5}) --squash --match-head-commit (?P<sha>[0-9a-f]{40})")
ASK_REASON = "دمج الطلب {pr} عند الرأس {sha} — يدمج في main وينشره Railway بعد نجاح الفحوص. الموافقة للمالك."


def owner_merge(command: str) -> re.Match[str] | None:
    return OWNER_MERGE.fullmatch(command.strip(" \t"))


def flatten(command: str) -> str:
    """ما ينفّذه الصدفة بعد إزالة التنصيص والهروب: `gh pr "mer"ge` و`mer\\ge` يصيران `merge`."""
    text = command.replace("\\\n", "")
    text = re.sub(r"\\(.)", r"\1", text)
    return text.replace("'", "").replace('"', "")


def hits(command: str) -> list[str]:
    text = _DATA_HEREDOC.sub(r"\1", command)
    flat = flatten(text)
    found = [name for name, pattern in RULES if pattern.search(text) or pattern.search(flat)]
    deploy = bool(_DEPLOY_WORDS.search(_KNOWN_PATHS.sub(" ", flat)))
    if _GLUE_AT_COMMAND.search(text) or (deploy and _GLUE_ANYWHERE.search(text)):
        found.append("glued-expansion")
    if _INTERPRETER.search(text) and (deploy or _SPAWN.search(text)):
        found.append("inline-interpreter")
    return found


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    merge = owner_merge(command)
    if merge:
        decision = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": ASK_REASON.format(pr=merge["pr"], sha=merge["sha"][:8]),
        }
        # ensure_ascii: مخرج الخطّاف يُقرأ JSON مهما كان ترميز الطرفية.
        print(json.dumps({"hookSpecificOutput": decision}))
        return 0
    found = hits(command)
    if not found:
        return 0
    print(MESSAGE.format(rule=", ".join(found)), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
