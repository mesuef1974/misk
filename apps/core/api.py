"""API مُنمَّط بـ Django Ninja. المصادقة: جلسة Django (كوكي HttpOnly) + CSRF."""

from __future__ import annotations

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.security import django_auth

from . import selectors, services

api = NinjaAPI(title="مسك", version="1.0", docs_url="/docs/")


class MeOut(Schema):
    id: int
    username: str
    is_staff: bool


class AuditOut(Schema):
    id: int
    action: str
    target: str
    created_at: str


class PingOut(Schema):
    ok: bool
    site: str


@api.get("/ping", response=PingOut)
def ping(request: HttpRequest):
    from django.conf import settings

    return {"ok": True, "site": settings.SITE_TITLE}


@api.get("/me", response=MeOut, auth=django_auth)
def me(request: HttpRequest):
    user = request.user
    return {"id": user.pk, "username": user.get_username(), "is_staff": user.is_staff}


@api.get("/audit", response=list[AuditOut], auth=django_auth)
def audit(request: HttpRequest, limit: int = 50):
    if not request.user.is_staff:
        from ninja.errors import HttpError

        raise HttpError(403, "للمشرفين فقط")
    services.record_audit(
        action="audit.view", actor=request.user, request_id=request.headers.get("X-Request-ID", "")
    )
    return [
        {"id": row.pk, "action": row.action, "target": row.target, "created_at": row.created_at.isoformat()}
        for row in selectors.recent_audit(min(limit, 200))
    ]
