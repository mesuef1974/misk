#!/usr/bin/env python3
"""المشغّل المجدوَل: بطاقة ready → worktree → claude بصلاحيات مخفَّضة → فحص محلي → PR. كل خطوة حدث في الدفتر.

الصلاحيات: النموذج يكتب الشيفرة ويشغّل الاختبارات فقط. الدفع وفتح الطلب يفعلهما هذا السكربت بعد نجاح
prepush_check.py، والدمج بوابة CI وطابور الدمج. حارسا .claude/hooks/ يحجبان ما يتسرّب.

النموذج يعدّل الـ worktree بـ acceptEdits، فما فيه من فاحص لا يُوثق به وحده: قبل تشغيل الفحص يُرفض أي فرق
عن origin/main يمسّ مسارًا محظورًا (قائمة البوابة من origin/main)، فيبقى prepush_check.py المشغَّل هو نسخة main.

الرموز (د2 من مراجعة 2026-11-19 الثانية): النموذج والفحص ينفّذان شيفرة البطاقة (اختبارات، conftest)، و`DISALLOWED_TOOLS`
لا تحكم العمليات الفرعية. فيعملان في بيئة معزولة: لا متغيرات رموز، وإعداد gh فارغ، ومساعد اعتماد git مصفَّر، والفحص
بمجلد منزل مؤقت فوق ذلك. وكل أمر git بعد النموذج معزول أيضًا، فإعداد git يزرعه النموذج (fsmonitor، مرشّحات) لا يرث
الرموز. الرموز لا تظهر إلا في الدفع وفتح الطلب، وبعد التحقق من أن إعداد git وخطّافاته كما كانت قبل النموذج.
والدفع يدفع الإيداع المفحوص بالـSHA لا اسم الفرع، بلا خطّافات، فعملية متروكة لا تبدّل ما يُدفع.
الباقي خارج المستودع: مستخدم نظام مستقل للمشغّل، فمفاتيح SSH وإعداد railway في المنزل تبقى في متناول خطوة النموذج.

    python automation/runner.py --once [--dry-run] [--max-turns 40] [--model <id>]
يُجدوَل كل N دقائق؛ قفل automation/.lock يمنع تشغيلين متوازيين.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ledger  # noqa: E402
import merge_gate  # noqa: E402

ROOT = ledger.ROOT
WORKTREES = ROOT / ".worktrees"
LOCK = ROOT / "automation" / ".lock"
LOCK_STALE_SECONDS = 3 * 60 * 60

DISALLOWED_TOOLS = [
    "Bash(git push*)",
    "Bash(git merge*)",
    "Bash(git rebase*)",
    # بادئات `git -C .` و`git --git-dir` تلتفّ على ما سبق؛ الحارس يحجب الدفع أيضًا، وهذه طبقة ثانية.
    "Bash(git -*)",
    "Bash(gh *)",
    "Bash(railway*)",
    "Bash(*railway/cli*)",
    "Bash(curl*)",
    "Bash(rm -rf*)",
    "WebFetch",
]

PROMPT = """أنت تنفّذ بطاقة عمل واحدة في مستودع Django + Vue. اعمل داخل هذا المجلد فقط.

العنوان: {title}
المطلوب:
{body}

ما يُعدّ نجاحًا (يجب أن يتحقق باختبار أو سلوك قابل للتشغيل):
{success}

القواعد:
- لا تعدّل ملفات .github/ أو scripts/ أو security/ أو lockfiles أو requirements*.txt أو Dockerfile أو .railway/.
- كل تغيير في النماذج يرافقه makemigrations، وكل منطق في services.py لا في النماذج أو العروض.
- أضف اختبارًا يفشل قبل تغييرك وينجح بعده.
- في النهاية شغّل: python scripts/prepush_check.py --allow-missing، وأصلح ما يفشل.
- أودع تغييراتك بـ git add <مسارات صريحة> ثم git commit برسالة عربية واضحة. لا تدفع.
"""


def sh(cmd: list[str], cwd: Path = ROOT, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace", check=check, **kw)


# أجزاء أسماء متغيرات البيئة التي تحمل اعتمادًا (GH_TOKEN، GITHUB_TOKEN، RAILWAY_API_TOKEN، AWS_SECRET_ACCESS_KEY...).
SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "CREDENTIAL", "PRIVATE_KEY")
# بلا علامة في الاسم لكنها تفتح اعتمادًا: وكيل SSH وبرامج طلب كلمة المرور.
SECRET_NAMES = frozenset({"SSH_AUTH_SOCK", "GIT_ASKPASS", "SSH_ASKPASS"})
# اعتماد النموذج نفسه: claude لا يعمل بدونه، ولا يفتح GitHub ولا Railway.
MODEL_KEEP = frozenset({"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"})
HOME_VARS = ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME")


def is_secret(name: str) -> bool:
    upper = name.upper()
    return upper in SECRET_NAMES or any(marker in upper for marker in SECRET_MARKERS)


def isolated_env(scratch: Path, keep: frozenset[str] = frozenset(), home: bool = False) -> dict[str, str]:
    """بيئة لشيفرة غير موثوقة: بلا رموز، وgh بلا حساب، وgit بلا مساعد اعتماد ولا مفاتيح SSH ولا سؤال.

    `credential.helper` الفارغ في نطاق البيئة (يُقرأ آخرًا) يصفّر قائمة المساعدين كلها (manager من إعداد النظام).
    `home=True` يحوّل مجلدات المنزل إلى مجلد مؤقت فارغ: لا ~/.ssh ولا إعداد railway ولا ~/.gitconfig.
    """
    env = {name: value for name, value in os.environ.items() if name in keep or not is_secret(name)}
    gh_dir = scratch / "gh"
    gh_dir.mkdir(parents=True, exist_ok=True)
    env.update(
        GH_CONFIG_DIR=str(gh_dir),
        GH_PROMPT_DISABLED="1",
        GIT_TERMINAL_PROMPT="0",
        GCM_INTERACTIVE="never",
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="credential.helper",
        GIT_CONFIG_VALUE_0="",
        GIT_SSH_COMMAND="ssh -F none -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityFile=none -o IdentityAgent=none",
    )
    if home:
        home_dir = scratch / "home"
        home_dir.mkdir(parents=True, exist_ok=True)
        env.update(dict.fromkeys(HOME_VARS, str(home_dir)))
    return env


def git_fingerprint(path: Path, env: dict[str, str]) -> str:
    """بصمة ما ينفّذه git بصلاحيات من يستدعيه: الإعداد بكل نطاقاته وما يضمّه، وخطّافات المستودع المشترك.

    تُؤخذ بالبيئة الحقيقية (لا المعزولة) فترى ~/.gitconfig الذي سيقرؤه الدفع. تغيّرها بعد النموذج يعني أنه زرع
    مساعد اعتماد أو fsmonitor أو مرشّحًا أو pushurl أو خطّافًا يعمل حين يدفع المشغّل أو حين يعمل المالك في ROOT.
    """
    digest = hashlib.sha256()
    listing = sh(
        ["git", "config", "--list", "--show-origin", "--includes", "-z"],
        cwd=path,
        capture_output=True,
        env=env,
    )
    digest.update(listing.stdout.encode("utf-8", "surrogateescape"))
    common = sh(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=path,
        capture_output=True,
        env=env,
    )
    hooks = Path(common.stdout.strip()) / "hooks"
    for hook in sorted(hooks.rglob("*")) if hooks.is_dir() else []:
        if hook.is_file():
            digest.update(b"\0" + hook.relative_to(hooks).as_posix().encode() + b"\0" + hook.read_bytes())
    return digest.hexdigest()


def acquire_lock() -> bool:
    """قفل ذرّي: الإنشاء الحصري يفشل إن سبق مشغّل آخر، فلا نافذة بين الفحص والكتابة."""
    for _ in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - LOCK.stat().st_mtime
            except FileNotFoundError:
                continue
            if age < LOCK_STALE_SECONDS:
                print(f"مشغّل آخر يعمل (قفل عمره {int(age)} ث) — خروج")
                return False
            print("قفل قديم — يُزال")
            LOCK.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return True
    return False


def release_lock() -> None:
    LOCK.unlink(missing_ok=True)


def pick_card() -> str | None:
    ready = ledger.cards_in("ready")
    return ready[0] if ready else None


def make_worktree(card: str) -> tuple[Path, str]:
    WORKTREES.mkdir(exist_ok=True)
    branch = f"card/{card}"
    path = WORKTREES / card
    sh(["git", "fetch", "origin", "main"], check=False)
    if path.exists():
        return path, branch
    sh(["git", "worktree", "add", "-b", branch, str(path), "origin/main"])
    return path, branch


def run_model(
    path: Path, card: str, model: str | None, max_turns: int, env: dict[str, str] | None = None
) -> int:
    meta = ledger.first(card) or {}
    prompt = PROMPT.format(
        title=meta.get("title", card),
        body=meta.get("body", ""),
        success=meta.get("success", "غير محدد — حدّده أولًا في الاختبار"),
    )
    claude = shutil.which("claude") or "claude"
    cmd = [
        claude,
        "-p",
        prompt,
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "acceptEdits",
        "--disallowedTools",
        *DISALLOWED_TOOLS,
    ]
    if model:
        cmd += ["--model", model]
    proc = sh(cmd, cwd=path, check=False, env=env)
    return proc.returncode


def touched_forbidden(path: Path, env: dict[str, str] | None = None) -> list[str]:
    """مسارات الفرق عن origin/main (مودَعة أو لا) التي تطابق قائمة البوابة المقروءة من origin/main نفسه.

    القراءة من origin/main لا من الشجرة: الفرق المرفوض لا يخفّف القاعدة التي ترفضه. تعذّر القياس يمنع.
    """

    def out(*cmd: str) -> str:
        return sh(list(cmd), cwd=path, capture_output=True, env=env).stdout

    globs = merge_gate.forbidden_globs(out("git", "show", f"origin/main:{merge_gate.RULES}"))
    # الشجرة العاملة لا الإيداعات وحدها: تعديل غير مودَع على الفاحص يُشغَّل كما لو أُودع.
    listings = (
        out("git", "diff", "--no-renames", "-z", "--name-only", "origin/main"),
        out("git", "ls-files", "-z", "--others", "--exclude-standard"),
    )
    changed = sorted({name for listing in listings for name in listing.split("\0") if name})
    return [name for name in changed if merge_gate.path_forbidden(name, globs)]


def prepush(path: Path, env: dict[str, str] | None = None) -> bool:
    """الفحص بلا رموز: تصادم الهجرات يحتاج gh فيُعدّ غير مقيس (--allow-missing)، وCI يقيسه على الطلب."""
    proc = sh([sys.executable, "scripts/prepush_check.py", "--allow-missing"], cwd=path, check=False, env=env)
    return proc.returncode == 0


def unpushable(path: Path, head: str, env: dict[str, str] | None = None) -> str | None:
    """سبب يمنع الدفع، أو None: المدفوع هو الرأس المفحوص نفسه، بشجرة نظيفة وإيداعات فوق main."""

    def out(*cmd: str) -> str:
        return sh(list(cmd), cwd=path, capture_output=True, env=env).stdout.strip()

    if out("git", "status", "--porcelain"):
        return "dirty_tree"
    if out("git", "rev-parse", "HEAD") != head:
        return "head_moved"
    if out("git", "rev-list", "--count", "origin/main..HEAD") == "0":
        return "no_commits"
    return None


def push_and_open_pr(path: Path, branch: str, card: str, head: str, no_hooks: Path) -> str:
    """الخطوة الوحيدة التي ترى الرموز. تدفع الـSHA المفحوص لا اسم الفرع، فعملية متروكة حرّكت الفرع لا تغيّر
    ما يُدفع؛ وبلا خطّافات (`no_hooks` مجلد فارغ، و--no-verify) فلا يعمل pre-push ولا reference-transaction."""
    sh(
        [
            "git",
            "-c",
            f"core.hooksPath={no_hooks}",
            "push",
            "--no-verify",
            "origin",
            f"{head}:refs/heads/{branch}",
        ],
        cwd=path,
    )
    meta = ledger.first(card) or {}
    body = f"بطاقة `{card}`\n\n{meta.get('body', '')}\n\nالنجاح: {meta.get('success', '')}\n\n(يُكتب سطر الاعتماد هنا بعد المراجعة: اعتُمد من المالك — YYYY-MM-DD — الرأس sha8)"
    proc = sh(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            meta.get("title", card),
            "--body",
            body,
        ],
        cwd=path,
        capture_output=True,
    )
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--max-turns", type=int, default=40)
    args = ap.parse_args(argv)

    card = pick_card()
    if not card:
        print("لا بطاقات ready")
        return 0
    if args.dry_run:
        print(f"سيُلتقط: {card} → worktree .worktrees/{card} → claude → prepush → PR")
        return 0
    if not acquire_lock():
        return 0
    scratch = Path(tempfile.mkdtemp(prefix="misk-runner-"))
    try:
        ledger.append(card, "claimed", pid=os.getpid())
        path, branch = make_worktree(card)
        trusted = dict(os.environ)
        sealed = isolated_env(scratch / "model", keep=MODEL_KEEP)
        checking = isolated_env(scratch / "check", home=True)
        no_hooks = scratch / "no-hooks"
        no_hooks.mkdir()
        before = git_fingerprint(path, trusted)
        rc = run_model(path, card, args.model, args.max_turns, env=sealed)
        # بعد النموذج لا يمسّ git ببيئة فيها رموز إلا بعد أن تطابق البصمة.
        if git_fingerprint(path, trusted) != before:
            ledger.append(card, "blocked", reason="git_config_changed")
            print(
                "النموذج غيّر إعداد git أو خطّافاته — لا فحص ولا دفع؛ راجع `git config --list --show-origin` و.git/hooks"
            )
            return 1
        head = sh(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, env=checking).stdout.strip()
        ledger.append(card, "coded", exit_code=rc, head=head)
        try:
            forbidden = touched_forbidden(path, env=checking)
        except (subprocess.CalledProcessError, merge_gate.GateError) as exc:
            forbidden = [f"تعذّر القياس: {exc}"]
        if forbidden:
            ledger.append(card, "blocked", reason="forbidden_paths", head=head, paths=forbidden)
            print("الفرق يمسّ مسارات محظورة — لا فحص ولا دفع، والبطاقة تبقى في worktree للمراجعة")
            return 1
        if not prepush(path, env=checking):
            ledger.append(card, "prepush_failed", head=head)
            print("الفحص المحلي فشل — البطاقة تبقى في worktree للمراجعة")
            return 1
        ledger.append(card, "prepush_ok", head=head)
        blocker = unpushable(path, head, env=checking)
        if not blocker and git_fingerprint(path, trusted) != before:
            # الفحص نفّذ شيفرة البطاقة أيضًا: تُقاس البصمة ثانيةً قبل أول أمر يرى الرموز.
            blocker = "git_config_changed"
        if blocker:
            # الدفتر يقبل الحالات المعروفة وحدها؛ السبب حقل لا حالة.
            ledger.append(card, "blocked", reason=blocker, head=head)
            print(f"لا دفع ({blocker}) — البطاقة تبقى في worktree للمراجعة")
            return 1
        url = push_and_open_pr(path, branch, card, head, no_hooks)
        ledger.append(card, "pr_opened", url=url, head=head)
        print(f"PR: {url}")
        return 0
    finally:
        release_lock()
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
