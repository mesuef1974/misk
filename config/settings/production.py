from .base import *  # noqa: F403
from .base import env, env_bool

DEBUG = False

# خلف وكيل Railway: الطلب يصل HTTP والـ X-Forwarded-Proto يحمل https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Railway يكتب X-Forwarded-For بخانتين «العميل، الحافة» ويتجاهل ما يرسله العميل (مقيس 2026-11-18 عبر
# /api/diagnostics/client-address): عنوان الزائر هو الخانة الثانية من اليمين. بـ1 يُقفل الدخول على عنوان الحافة المشترك.
TRUSTED_PROXY_COUNT = int(env("TRUSTED_PROXY_COUNT", "2"))
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
# فاحص الصحة في Railway يسأل الحاوية بـ HTTP بلا X-Forwarded-Proto: تحويله إلى HTTPS (301) يُفشل الفحص.
# الاستثناء لمسار الصحة وحده؛ لا بيانات فيه ولا جلسة.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# سنة: الحد الأدنى الموصى به (OWASP). لا preload: النطاق الحالي فرعي من up.railway.app لا نملكه.
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False

if not env("ALLOWED_HOSTS"):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("ALLOWED_HOSTS مطلوب في الإنتاج")

if not env("DATABASE_URL"):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("DATABASE_URL مطلوب في الإنتاج")
