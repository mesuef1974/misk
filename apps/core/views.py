"""صحة الخدمة (لـ Railway healthcheck)، وrobots.txt، وقشرة SPA التي يحقن فيها django-vite حزم Vue.

كلها تقبل HEAD مع GET (`require_safe`): أدوات مراقبة التوفر تسأل بـ HEAD.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

# المنصة لحسابات المشرفين وحدها: لا شيء فيها للفهرسة.
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


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
def spa(request: HttpRequest) -> HttpResponse:
    return render(request, "spa.html")
