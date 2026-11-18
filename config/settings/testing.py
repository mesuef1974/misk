import os

os.environ.setdefault("SECRET_KEY", "ci-testing-only")  # noqa: S105

from .base import *  # noqa: E402, F403

DEBUG = False
ALLOWED_HOSTS = ["*"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AXES_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_STORE_EAGER_RESULT = True  # كي يقرأ مسار الاستطلاع نتيجة المهمة كما في الإنتاج
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
DJANGO_VITE["default"]["dev_mode"] = True  # noqa: F405 — لا يحتاج manifest في الاختبار
