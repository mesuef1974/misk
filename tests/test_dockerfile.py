"""صورة التشغيل: مستخدم التشغيل لا يملك /app ولا الشيفرة، بل staticfiles وmedia وحدهما (د7)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runtime_stage() -> list[str]:
    """أوامر المرحلة الأخيرة، كل أمر سطر واحد (تُضمّ الأسطر المكسورة بـ\\)."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    stage = re.split(r"^FROM ", text, flags=re.M)[-1]
    joined = re.sub(r"\\\n\s*", " ", stage)
    return [
        line.strip() for line in joined.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


def test_only_writable_dirs_are_given_to_the_app_user():
    targets = []
    for line in runtime_stage():
        for match in re.finditer(r"chown\s+(?:-\S+\s+)*\S+\s+([^&;]+)", line):
            targets += match.group(1).split()
    assert targets, "لا chown في صورة التشغيل: staticfiles وmedia يحتاجانه"
    assert sorted(targets) == ["/app/media", "/app/staticfiles"]


def test_app_dir_is_not_chowned_before_the_code_is_copied():
    commands = runtime_stage()
    copy_code = next(i for i, line in enumerate(commands) if line.startswith("COPY . ."))
    assert not any("chown" in line for line in commands[:copy_code])
    assert not any(re.search(r"useradd\b.*\s-m\b", line) for line in commands), (
        "useradd -m ينشئ /app ملكًا لـapp"
    )


def test_runtime_runs_as_the_app_user():
    assert [line for line in runtime_stage() if line.startswith("USER ")] == ["USER app"]
