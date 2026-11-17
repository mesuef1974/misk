"""API مُنمَّط بـ Django Ninja. المصادقة: جلسة Django (كوكي HttpOnly) + CSRF."""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest
from django.urls import reverse
from ninja import Field, NinjaAPI, Query, Schema
from ninja.errors import HttpError
from ninja.security import django_auth
from ninja.utils import check_csrf

from . import selectors, services
from .auth import client_ip, request_id, staff_auth

# الوثائق ومخطط OpenAPI يكشفان كل المسارات والمخططات: للمشرفين فقط، وغيرهم يُحوَّل إلى دخول لوحة الإدارة.
api = NinjaAPI(title="مسك", version="1.0", docs_url="/docs/", docs_decorator=staff_member_required)


class MeOut(Schema):
    id: int
    username: str
    is_staff: bool
    # مسار لوحة الإدارة يُضبط بـ ADMIN_URL وقد يكون غير المعتاد: لا يُكشف إلا للمشرف.
    admin_url: str | None


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


class ClientAddressOut(Schema):
    remote_addr: str
    x_forwarded_for: str
    x_real_ip: str
    trusted_proxy_count: int
    client_ip: str


@api.get("/ping", response=PingOut)
def ping(request: HttpRequest):
    from django.conf import settings

    return {"ok": True, "site": settings.SITE_TITLE}


def _me(user) -> dict:
    return {
        "id": user.pk,
        "username": user.get_username(),
        "is_staff": user.is_staff,
        "admin_url": reverse("admin:index") if user.is_staff else None,
    }


@api.get("/me", response=MeOut, auth=django_auth)
def me(request: HttpRequest):
    return _me(request.user)


@api.get("/diagnostics/client-address", response=ClientAddressOut, auth=staff_auth)
def client_address(request: HttpRequest):
    """ما يصل التطبيق من عنوان الطالب نفسه: للتحقق من أن `TRUSTED_PROXY_COUNT` يطابق وكيل النشر.

    العنوان المحسوب `client_ip` هو ما يُقفل عليه الدخول؛ يجب أن يساوي عنوان المتصفح العام.
    """
    from django.conf import settings

    return {
        "remote_addr": request.META.get("REMOTE_ADDR", ""),
        "x_forwarded_for": request.META.get("HTTP_X_FORWARDED_FOR", ""),
        "x_real_ip": request.META.get("HTTP_X_REAL_IP", ""),
        "trusted_proxy_count": settings.TRUSTED_PROXY_COUNT,
        "client_ip": client_ip(request) or "",
    }


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
def audit(request: HttpRequest, limit: int = Query(50, ge=1)):
    if not request.user.is_staff:
        raise HttpError(403, "للمشرفين فقط")
    services.record_audit(action="audit.view", actor=request.user, request_id=request_id(request))
    return [
        {"id": row.pk, "action": row.action, "target": row.target, "created_at": row.created_at.isoformat()}
        for row in selectors.recent_audit(min(limit, 200))
    ]
