"""طبقة الخدمات: كل عملية كتابة تمرّ من هنا، idempotent حيث أمكن، وتسجّل في AuditLog."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest

from .models import AuditLog


@transaction.atomic
def record_audit(
    *,
    action: str,
    actor: AbstractBaseUser | None = None,
    target: str = "",
    payload: dict[str, Any] | None = None,
    request_id: str = "",
) -> AuditLog:
    """idempotent على (action, target, request_id) عندما يُمرَّر request_id."""
    if request_id:
        existing = AuditLog.objects.filter(action=action, target=target, request_id=request_id).first()
        if existing:
            return existing
    return AuditLog.objects.create(
        action=action,
        actor=actor if getattr(actor, "pk", None) else None,
        target=target,
        payload=payload or {},
        request_id=request_id,
    )


class SignInError(Exception):
    """رفض تسجيل الدخول. `status` هو رمز HTTP الذي يعيده المسار."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def sign_in(request: HttpRequest, *, username: str, password: str, request_id: str = "") -> AbstractBaseUser:
    """جلسة لمشرف فقط. الرسالة واحدة للاسم الخاطئ وكلمة المرور الخاطئة والحساب الموقوف.

    المحاولات الفاشلة والقفل بعد تكرارها يسجّلهما django-axes (يحتاج `request` في authenticate)،
    و`login` يبدّل مفتاح الجلسة ورمز CSRF (لا تثبيت للجلسة).
    """
    user = authenticate(request, username=username, password=password)
    if user is None:
        raise SignInError(401, "اسم المستخدم أو كلمة المرور غير صحيحة")
    if not user.is_staff:
        raise SignInError(403, "هذا الحساب ليس حساب مشرف")
    login(request, user)
    record_audit(action="auth.login", actor=user, target=f"user:{user.pk}", request_id=request_id)
    return user


def sign_out(request: HttpRequest, *, request_id: str = "") -> None:
    """idempotent: الخروج بلا جلسة لا يفعل شيئًا."""
    user = request.user
    if not user.is_authenticated:
        return
    record_audit(action="auth.logout", actor=user, target=f"user:{user.pk}", request_id=request_id)
    logout(request)
