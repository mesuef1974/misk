"""طبقة الخدمات: كل عملية كتابة تمرّ من هنا، idempotent حيث أمكن، وتسجّل في AuditLog."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from .columns import column_length
from .models import AuditLog

REQUEST_ID_LENGTH = column_length(AuditLog, "request_id")
# حدّ ثانٍ فوق قفل axes بالزوج (اسم، عنوان): تدوير العناوين لا يتيح أكثر من هذا العدد من التخمين
# على اسم واحد في النافذة. أعلى من حدّ الزوج كي لا يقفل زائرٌ عابر مشرفًا يعرف اسمه.
NAME_FAILURE_LIMIT = 30
NAME_FAILURE_WINDOW_S = 60 * 60
NAME_LOCKED = "محاولات كثيرة على هذا الحساب؛ أعد المحاولة بعد ساعة"


def record_audit(
    *,
    action: str,
    actor: AbstractBaseUser | None = None,
    target: str = "",
    payload: dict[str, Any] | None = None,
    request_id: str = "",
) -> AuditLog:
    """idempotent على (action, target, request_id) عندما يُمرَّر request_id، ولو تزامن الطلبان:
    قيد التفرّد يرفض الثاني فيُعاد صف الأول.

    `request_id` يأتي من ترويسة يكتبها العميل؛ ما زاد على طول العمود يُقصّ بدل أن يُسقط الطلب.
    لا يُمرَّر لأحداث لا تُعاد (الدخول، الخروج، الاطّلاع): ترويسة مكرَّرة كانت ستُسقط الحدث الثاني من السجل.
    """
    request_id = request_id[:REQUEST_ID_LENGTH]
    known = actor if getattr(actor, "pk", None) else None
    row = AuditLog(
        action=action,
        actor_id=known.pk if known else None,
        actor_name=known.get_username() if known else "",
        target=target,
        payload=payload or {},
        request_id=request_id,
    )
    if not request_id:
        row.save()
        return row

    def existing_row() -> AuditLog | None:
        return AuditLog.objects.filter(action=action, target=target, request_id=request_id).first()

    existing = existing_row()
    if existing:
        return existing
    try:
        with transaction.atomic():  # نقطة حفظ: فشل القيد لا يُفسد معاملة المستدعي
            row.save()
    except IntegrityError:
        existing = existing_row()
        if existing is None:
            raise
        return existing
    return row


class SignInError(Exception):
    """رفض تسجيل الدخول. `status` هو رمز HTTP الذي يعيده المسار."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def sign_in(request: HttpRequest, *, username: str, password: str) -> AbstractBaseUser:
    """جلسة لمشرف فقط. الرد واحد للاسم الخاطئ وكلمة المرور الخاطئة والحساب الموقوف وغير المشرف،
    فلا يُعرف من الرد أن كلمة مرور حساب غير مشرف صحيحة.

    المحاولات الفاشلة والقفل بعد تكرارها يسجّلهما django-axes (يحتاج `request` في authenticate)،
    و`login` يبدّل مفتاح الجلسة ورمز CSRF (لا تثبيت للجلسة).
    """
    throttled = getattr(settings, "AXES_ENABLED", True)
    failures_key = _name_failures_key(username)
    if throttled and cache.get(failures_key, 0) >= NAME_FAILURE_LIMIT:
        raise SignInError(429, NAME_LOCKED)
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_staff:
        if throttled:
            _count_name_failure(failures_key)
        raise SignInError(401, "اسم المستخدم أو كلمة المرور غير صحيحة")
    login(request, user)
    record_audit(action="auth.login", actor=user, target=f"user:{user.pk}")
    return user


def _name_failures_key(username: str) -> str:
    # بصمة لا الاسم نفسه: مفتاح الذاكرة المؤقتة بطول ثابت ولا يحمل ما كتبه الزائر.
    digest = hashlib.sha256(username.strip().casefold().encode()).hexdigest()
    return f"signin-failures:{digest}"


def _count_name_failure(key: str) -> None:
    """نافذة ثابتة تبدأ من أول فشل؛ `add` ثم `incr` ذرّيّان في Redis فلا يضيع فشل بين طلبين متزامنين."""
    cache.add(key, 0, NAME_FAILURE_WINDOW_S)
    try:
        cache.incr(key)
    except ValueError:  # انتهت النافذة بين add وincr
        cache.add(key, 1, NAME_FAILURE_WINDOW_S)


def sign_out(request: HttpRequest) -> None:
    """idempotent: الخروج بلا جلسة لا يفعل شيئًا."""
    user = request.user
    if not user.is_authenticated:
        return
    record_audit(action="auth.logout", actor=user, target=f"user:{user.pk}")
    logout(request)
