"""فحص صحة العامل (د8): لا ينجح قبل أن يكتب Celery ملف الجاهزية، فلا يُسقط Railway العامل السابق قبل أوانه."""

import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from config import celery as celery_config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import worker_health  # noqa: E402


@pytest.fixture
def ready_file(tmp_path, monkeypatch):
    path = tmp_path / "ready"
    monkeypatch.setenv("WORKER_READY_FILE", str(path))
    return path


@pytest.fixture
def health(ready_file):
    server = worker_health.serve(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path: str) -> int:
        try:
            with urllib.request.urlopen(base + path, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    yield get
    server.shutdown()
    server.server_close()


def test_health_fails_until_celery_is_ready_and_again_after_shutdown(health, ready_file):
    assert health("/health/") == 503
    celery_config.mark_ready()
    assert ready_file.exists()
    assert health("/health/") == 200
    assert health("/health/?probe=1") == 200
    celery_config.mark_not_ready()
    assert not ready_file.exists()
    assert health("/health/") == 503


def test_health_serves_only_its_path(health, ready_file):
    ready_file.touch()
    assert health("/") == 404
    assert health("/admin/") == 404


def test_signals_do_nothing_without_ready_file_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKER_READY_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    celery_config.mark_ready()
    celery_config.mark_not_ready()
    assert list(tmp_path.iterdir()) == []


def test_worker_service_is_gated_by_its_health_check():
    """بلا فحص صحة يحلّ العامل الجديد محلّ السابق فور بدئه، ولو لم تُطبَّق هجراته أبدًا."""
    config = (ROOT / ".railway" / "railway.ts").read_text(encoding="utf-8")
    worker = config[config.index('service("worker"') :]
    worker = worker[: worker.index("});")]
    assert 'healthcheck: "/health/"' in worker
    timeout = re.search(r"healthcheckTimeout: (\d+)", worker)
    assert timeout, "مهلة فحص صحة العامل غائبة"
    script = (ROOT / "scripts" / "railway-worker.sh").read_text(encoding="utf-8")
    wait = re.search(r"WORKER_MIGRATION_WAIT_S:-(\d+)", script)
    assert wait
    # المهلة فوق انتظار الهجرات، فيظهر سبب العامل في سجله قبل أن يقطعه Railway.
    assert int(timeout.group(1)) > int(wait.group(1))
