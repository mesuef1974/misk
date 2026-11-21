"""الإعدادات المشتركة. كل ما يختلف بين البيئات يُقرأ من المتغيرات، ولا أسرار في الشيفرة."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(f"المتغير {name} مطلوب")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
ADMIN_URL = env("ADMIN_URL", "admin/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_vite",
    "apps.core.axes_app.MiskAxesConfig",  # axes باسم عربي في لوحة الإدارة
    "apps.core",
    "apps.catalog",
    "apps.orders",
    "apps.production",
    "apps.designs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # لا LocaleMiddleware: الموقع عربي أولًا مهما كان Accept-Language للمتصفح.
    # عند الحاجة لتبديل اللغة أضفه مع i18n_patterns، وسيتبعه dir/lang في spa.html تلقائيًا.
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.config(
        default=env("DATABASE_URL", "postgres://misk:misk@localhost:5432/misk"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # ساعة
# القفل بالزوج (اسم، عنوان) لا بأيٍّ منهما: محاولات زائر لا تقفل غيره، ومعرفة اسم مشرف لا تكفي لقفله.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
# عدد الوكلاء الموثوقين أمام التطبيق؛ 0 = اتصال مباشر فيُؤخذ REMOTE_ADDR ويُهمَل X-Forwarded-For.
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "0"))
AXES_CLIENT_IP_CALLABLE = "apps.core.auth.client_ip"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Qatar"
USE_I18N = True
USE_TZ = True

# الملفات الثابتة: Vite يبني إلى frontend_dist بمعرّف محتوى في اسم كل ملف، وWhiteNoise يخدمها مضغوطة.
# لا نستعمل Manifest storage من Django: هو يعيد تسمية ملف الدخول بينما الأجزاء الكسولة تستورد الاسم الأصلي،
# فيُنفَّذ main.ts مرتين ويُركَّب التطبيق مرتين على #app (صفحة فارغة + TypeError nextSibling).
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
_FRONTEND_DIST = BASE_DIR / "frontend_dist"
STATICFILES_DIRS: list = [_FRONTEND_DIST] if _FRONTEND_DIST.exists() else []  # يغيب قبل أول npm run build
# ألوان المنصة مصدر واحد في الواجهة؛ لوحة Django تقرؤها من /static/brand/tokens.css (templates/admin/base_site.html).
# المجلد يحمل البادئة brand/ في بنيته لا في الإعداد: بادئة STATICFILES_DIRS لا يطابقها الباحث على ويندوز.
STATICFILES_DIRS.append(BASE_DIR / "frontend" / "src" / "static")
STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
_VITE_HASHED = re.compile(r"/assets/[^/]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9.]+$")


def _immutable_static(path: str, url: str) -> bool:
    """ملفات Vite معرَّفة بالمحتوى → cache-control immutable؛ البقية (admin) بالافتراضي القصير."""
    return bool(_VITE_HASHED.search(url))


WHITENOISE_IMMUTABLE_FILE_TEST = _immutable_static
# whitenoise لا يعرف .webmanifest فيرسله application/octet-stream.
WHITENOISE_MIMETYPES = {".webmanifest": "application/manifest+json"}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# الويب والعامل خدمتان منفصلتان في الإنتاج، والقرص الدائم يُركَّب على خدمة واحدة: الوسائط في مخزن كائنات S3
# يقرؤه الاثنان. بلا MEDIA_S3_BUCKET يبقى القرص المحلي (التطوير والاختبار). الدلو خاص، والعرض عبر
# `apps.core.views.media_file` للمشرفين وحدهم، فلا روابط موقَّعة تخرج إلى المتصفح.
# الاحتياط بأسماء AWS_* هو ما يضيفه زر «Add to Service» في دلو Railway؛ والقيمة الفارغة (إشارة
# `${{...}}` لم تُحلَّ) تُعامَل كالغائبة فيُنتقل إلى الاسم التالي.
_MEDIA_S3_FALLBACKS: dict[str, tuple[str, ...]] = {
    "MEDIA_S3_BUCKET": ("AWS_S3_BUCKET_NAME", "AWS_STORAGE_BUCKET_NAME"),
    "MEDIA_S3_ENDPOINT": ("AWS_ENDPOINT_URL_S3", "AWS_ENDPOINT_URL", "AWS_S3_ENDPOINT_URL"),
    "MEDIA_S3_REGION": ("AWS_DEFAULT_REGION", "AWS_REGION", "AWS_S3_REGION_NAME"),
    "MEDIA_S3_ACCESS_KEY_ID": ("AWS_ACCESS_KEY_ID",),
    "MEDIA_S3_SECRET_ACCESS_KEY": ("AWS_SECRET_ACCESS_KEY",),
}


def media_s3_env(name: str, *, required: bool = False) -> str:
    """أول قيمة غير فارغة من MEDIA_S3_* ثم بدائلها AWS_*؛ رسالة الخطأ تسمّي الاسم الأساسي."""
    for candidate in (name, *_MEDIA_S3_FALLBACKS.get(name, ())):
        if value := env(candidate):
            return value
    return env(name, required=required)


MEDIA_S3_BUCKET = media_s3_env("MEDIA_S3_BUCKET")
if MEDIA_S3_BUCKET:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": MEDIA_S3_BUCKET,
            "endpoint_url": media_s3_env("MEDIA_S3_ENDPOINT") or None,
            "region_name": media_s3_env("MEDIA_S3_REGION") or None,
            "access_key": media_s3_env("MEDIA_S3_ACCESS_KEY_ID", required=True),
            "secret_key": media_s3_env("MEDIA_S3_SECRET_ACCESS_KEY", required=True),
            "location": env("MEDIA_S3_PREFIX", "media"),
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
            "addressing_style": env("MEDIA_S3_ADDRESSING_STYLE") or None,
            "signature_version": "s3v4",
        },
    }

DJANGO_VITE = {
    "default": {
        "dev_mode": False,
        "manifest_path": BASE_DIR / "frontend_dist" / ".vite" / "manifest.json",
        "static_url_prefix": "",
    }
}

# الجلسات والكوكيز: HttpOnly + Secure + SameSite (قاعدة الأمن).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # Vue يقرأه من الكوكي لإرسال X-CSRFToken
SESSION_COOKIE_AGE = 60 * 60 * 8
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
# كل شيء من أصل الموقع وحده: الواجهة مبنية في ملفات (لا سكربت مضمَّن)، ولا خطوط ولا صور خارجية.
# 'unsafe-inline' للأنماط فقط (خصائص style التي يكتبها Vue ولوحة الإدارة)؛ السكربتات بلا استثناء.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

REDIS_URL = env("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = REDIS_URL or "cache+memory://"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_ALWAYS_EAGER = False
# نتيجة مهمة التخطيط تُقرأ بالاستطلاع ثم لا حاجة إليها؛ ساعة تكفي ولا تملأ Redis.
CELERY_RESULT_EXPIRES = 60 * 60

# تخطيط الألواح في عامل Celery بدل الطلب نفسه (قاعدة 300ms). يشترط عاملًا وRedis مشتركًا بين الويب والعامل،
# فهو معطَّل افتراضًا: بلاهما تبقى المهمة في طابور لا يقرؤه أحد ويتعطّل التخطيط كله.
PLANNING_ASYNC = env_bool("PLANNING_ASYNC", False)

SITE_TITLE = "مسك"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
