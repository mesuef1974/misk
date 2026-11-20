"""railway-worker.sh يُشغَّل كما هو ببدائل لـpython وcelery وsleep: الانتظار والعطل لا يختلطان (د8)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.core.management.commands.pending_migrations import PENDING_EXIT

ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which("sh")
pytestmark = pytest.mark.skipif(SHELL is None, reason="لا sh في هذه البيئة")


def stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture
def worker(tmp_path):
    """يشغّل العامل؛ `answers` رموز فحص الهجرات بالترتيب ومخرجاتها، والأخير يتكرر."""

    def run(answers: list[tuple[int, str]], wait_s: int = 30) -> subprocess.CompletedProcess:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        cases = "\n".join(
            f'  {i}) echo "{text}"; exit {code} ;;' for i, (code, text) in enumerate(answers[:-1], start=1)
        )
        last_code, last_text = answers[-1]
        counter = tmp_path / "count"
        stub(
            bin_dir,
            "python",
            f"""case "$*" in
*pending_migrations*)
  n=$(( $(cat "{counter.as_posix()}" 2>/dev/null || echo 0) + 1 )); echo $n > "{counter.as_posix()}"
  case $n in
{cases}
  *) echo "{last_text}" >&2; exit {last_code} ;;
  esac ;;
*collectstatic*) echo collected ;;
*worker_health.py*) echo "health ready_file=$([ -e "$WORKER_READY_FILE" ] && echo stale || echo clean)" > "{(tmp_path / "health").as_posix()}" ;;
esac""",
        )
        ready = tmp_path / "ready"
        ready.touch()  # بقية تشغيل سابق: لا تُنجح فحص الصحة قبل أن يجهز هذا العامل.
        stub(bin_dir, "celery", 'echo "celery started"')
        stub(bin_dir, "sleep", ":")
        env = {
            **os.environ,
            "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}",
            "REDIS_URL": "redis://x",
            "DATABASE_URL": "postgres://x",
            "WORKER_MIGRATION_WAIT_S": str(wait_s),
            "WORKER_READY_FILE": ready.as_posix(),
        }
        assert SHELL is not None
        return subprocess.run(
            [SHELL, str(ROOT / "scripts" / "railway-worker.sh")],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    return run


def test_worker_waits_for_pending_migrations_then_starts(worker):
    done = worker([(PENDING_EXIT, "1 هجرة غير مطبَّقة: orders.0003"), (0, "")])
    assert done.returncode == 0
    assert "celery started" in done.stdout
    assert "هجرات غير مطبَّقة: 1 هجرة غير مطبَّقة: orders.0003" in done.stderr


def test_health_check_starts_first_without_a_stale_ready_file(worker, tmp_path):
    """د8: فحص الصحة يبدأ قبل انتظار الهجرات، وجاهزية تشغيل سابق لا تُحسب لهذا العامل."""
    done = worker([(PENDING_EXIT, "1 هجرة غير مطبَّقة: orders.0003")], wait_s=20)
    assert done.returncode == 1
    assert (tmp_path / "health").read_text(encoding="utf-8").strip() == "health ready_file=clean"
    assert not (tmp_path / "ready").exists()


def test_database_error_is_reported_as_an_error_not_as_pending_migrations(worker):
    done = worker([(1, "OperationalError: could not connect to server")], wait_s=20)
    assert done.returncode == 1
    assert "celery started" not in done.stdout
    assert "تعذّر فحص الهجرات (رمز 1)" in done.stderr
    assert "could not connect to server" in done.stderr
    assert "هجرات غير مطبَّقة" not in done.stderr


def test_worker_gives_up_on_migrations_that_never_apply(worker):
    done = worker([(PENDING_EXIT, "1 هجرة غير مطبَّقة: orders.0003")], wait_s=20)
    assert done.returncode == 1
    assert "celery started" not in done.stdout
    assert "::error:: العامل لا يبدأ بعد 20 ث — هجرات غير مطبَّقة" in done.stderr
