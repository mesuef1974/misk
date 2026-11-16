"""Celery: المهام الأطول من 300ms تذهب هنا (قاعدة المشروع). المهام idempotent دائمًا."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("misk")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
