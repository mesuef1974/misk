"""صحة الخدمة (لـ Railway healthcheck)، وrobots.txt، وملفات media، وقشرة SPA التي يحقن فيها django-vite
حزم Vue.

كلها تقبل HEAD مع GET (`require_safe`): أدوات مراقبة التوفر تسأل بـ HEAD.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils._os import safe_join
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

# المنصة لحسابات المشرفين وحدها: لا شيء فيها للفهرسة.
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"

# ما يُعرض في المتصفح؛ غيره (PDF، DXF، نص...) يُنزَّل مرفقًا.
MEDIA_INLINE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"})
# SVG مستند قد يحمل سكربتًا: الصندوق الرملي يمنعه ويعزله عن أصل المنصة وجلستها، ويبقى الرسم ظاهرًا.
MEDIA_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


@require_safe
@never_cache
def health(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db = "ok"
        status = 200
    except Exception:  # noqa: BLE001
        db = "down"
        status = 503
    return JsonResponse({"status": "ok" if status == 200 else "degraded", "db": db}, status=status)


@require_safe
def robots_txt(request: HttpRequest) -> HttpResponse:
    return HttpResponse(ROBOTS_TXT, content_type="text/plain; charset=utf-8")


@require_safe
def media_file(request: HttpRequest, path: str) -> FileResponse:
    """ملفات MEDIA_ROOT للمشرفين وحدهم: فيها أصول تصاميم مرخّصة من البائعين لا تُنشر.

    غير المشرف يرى 404 لا 403، فلا يعرف أي المسارات موجود. `safe_join` يرفض الخروج من MEDIA_ROOT.
    """
    user = request.user
    if not (user.is_authenticated and user.is_active and user.is_staff):
        raise Http404
    try:
        full = Path(safe_join(settings.MEDIA_ROOT, path))
    except SuspiciousFileOperation as exc:
        raise Http404 from exc
    if not full.is_file():
        raise Http404
    inline = full.suffix.lower() in MEDIA_INLINE_SUFFIXES
    response = FileResponse(full.open("rb"), as_attachment=not inline, filename=full.name)
    response.headers["Content-Security-Policy"] = MEDIA_CSP
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["Vary"] = "Cookie"
    return response


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    return render(request, "spa.html")
