"""API مُنمَّط بـ Django Ninja. المصادقة: جلسة Django (كوكي HttpOnly) + CSRF."""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Field, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import django_auth
from ninja.utils import check_csrf

from . import selectors, services
from .auth import request_id

api = NinjaAPI(title="مسك", version="1.0", docs_url="/docs/")


class MeOut(Schema):
    id: int
    username: str
    is_staff: bool


class LoginIn(Schema):
    # الحدّان يمنعان إرسال نص طويل إلى دالة التجزئة (استنزاف المعالج).
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=128)


class OkOut(Schema):
    ok: bool


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


def _me(user) -> dict:
    return {"id": user.pk, "username": user.get_username(), "is_staff": user.is_staff}


@api.get("/me", response=MeOut, auth=django_auth)
def me(request: HttpRequest):
    return _me(request.user)


@api.post("/auth/login", response=MeOut)
def login(request: HttpRequest, payload: LoginIn):
    # المسار بلا auth فلا يفحص Ninja رمز CSRF؛ نفحصه هنا كي لا يُدخَل الضحية بحساب غيره (login CSRF).
    if check_csrf(request) is not None:
        raise HttpError(403, "رمز CSRF مفقود أو غير صالح؛ حدّث الصفحة")
    try:
        user = services.sign_in(
            request, username=payload.username, password=payload.password, request_id=request_id(request)
        )
    except services.SignInError as exc:
        raise HttpError(exc.status, str(exc)) from exc
    return _me(user)


@api.post("/auth/logout", response=OkOut, auth=django_auth)
def logout(request: HttpRequest):
    services.sign_out(request, request_id=request_id(request))
    return {"ok": True}


@api.get("/audit", response=list[AuditOut], auth=django_auth)
def audit(request: HttpRequest, limit: int = 50):
    if not request.user.is_staff:
        raise HttpError(403, "للمشرفين فقط")
    services.record_audit(action="audit.view", actor=request.user, request_id=request_id(request))
    return [
        {"id": row.pk, "action": row.action, "target": row.target, "created_at": row.created_at.isoformat()}
        for row in selectors.recent_audit(min(limit, 200))
    ]
