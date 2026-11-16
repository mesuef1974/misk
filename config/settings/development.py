import os

os.environ.setdefault("SECRET_KEY", "dev-only-not-for-production")  # noqa: S105

from .base import *  # noqa: E402, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
INTERNAL_IPS = ["127.0.0.1"]
DJANGO_VITE["default"]["dev_mode"] = True  # noqa: F405
DJANGO_VITE["default"]["dev_server_port"] = 5173  # noqa: F405
CONTENT_SECURITY_POLICY = ""  # خادم Vite على أصل آخر (5173) مع HMR عبر WebSocket
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]
AXES_ENABLED = False
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
