"""Celery: المهام الأطول من 300ms تذهب هنا (قاعدة المشروع). المهام idempotent دائمًا."""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("misk")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def _ready_file() -> Path | None:
    # يضبطه scripts/railway-worker.sh وحده؛ في غيره لا ملف جاهزية.
    path = os.environ.get("WORKER_READY_FILE")
    return Path(path) if path else None


@worker_ready.connect
def mark_ready(**_: object) -> None:
    """فحص صحة العامل (scripts/worker_health.py) ينجح من هنا لا قبله (د8)."""
    if path := _ready_file():
        path.touch()


@worker_shutdown.connect
def mark_not_ready(**_: object) -> None:
    if path := _ready_file():
        path.unlink(missing_ok=True)
