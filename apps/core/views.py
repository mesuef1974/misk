"""عرضان فقط: صحة الخدمة (لـ Railway healthcheck) وقشرة SPA التي يحقن فيها django-vite حزم Vue."""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
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


@require_GET
def spa(request: HttpRequest) -> HttpResponse:
    return render(request, "spa.html")
