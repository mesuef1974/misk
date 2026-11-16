"""حزمة الإعدادات. Celery اختياري: إن حُذف config/celery.py في التوليد يبقى الاستيراد صامتًا."""

try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover - بلا Celery
    celery_app = None

__all__ = ("celery_app",)
