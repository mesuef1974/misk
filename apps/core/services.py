"""طبقة الخدمات: كل عملية كتابة تمرّ من هنا، idempotent حيث أمكن، وتسجّل في AuditLog."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from axes.handlers.proxy import AxesProxyHandler
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpRequest

from .columns import column_length
from .models import AuditLog

REQUEST_ID_LENGTH = column_length(AuditLog, "request_id")
# حدّ ثانٍ فوق قفل axes بالزوج (اسم، عنوان): تدوير العناوين لا يتيح أكثر من هذا العدد من التخمين
# على اسم واحد في النافذة. يحجب الأجهزة التي لم يُدخَل منها بهذا الاسم وحدها: الجهاز الذي دخل منه
# صاحب الحساب يحمل كوكي موقَّعًا (نمط «كوكي الجهاز» في OWASP) فيُعدّ فشله عليه لا على الاسم،
# ولا يقفله غريبٌ يعرف الاسم.
# بلوغ الحدّ يبطّئ ولا يقفل (ح1 من مراجعة 2026-11-20): تُجرَّب كلمة مرور واحدة كل NAME_SLOW_INTERVAL_S
# للعدّاد، وما سواها يُرفض بلا تجربة. فالتخمين الموزَّع يبقى نحو 180 في الساعة، والمشرف على جهاز جديد
# يدخل حين يصيب الفرصة، ودخوله يصفّر العدّاد.
NAME_FAILURE_LIMIT = 30
NAME_FAILURE_WINDOW_S = 60 * 60
NAME_SLOW_INTERVAL_S = 20
NAME_LOCKED = "محاولات كثيرة على هذا الحساب من أجهزة لم يُدخَل منها؛ ادخل من جهاز دخلت منه سابقًا أو أعد المحاولة بعد نصف دقيقة"
DEVICE_COOKIE = "misk_signin_device"
DEVICE_MAX_AGE_S = 60 * 60 * 24 * 90
_DEVICE_SALT = "apps.core.services.signin-device"


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
    device = _known_device(request, username)
    failures_key = _device_failures_key(device) if device else _name_failures_key(username)
    slowed = throttled and cache.get(failures_key, 0) >= NAME_FAILURE_LIMIT
    # `add` ذرّي: طلب واحد يأخذ الفرصة في كل فترة، وما سواه لا يجرّب كلمة المرور.
    if slowed and not cache.add(_slow_slot_key(failures_key), 1, NAME_SLOW_INTERVAL_S):
        raise SignInError(429, NAME_LOCKED)
    # ما يرفضه axes لقفل الزوج لا يجرّب كلمة المرور، فلا يُعدّ: عدّه كان يتيح لعنوان واحد قفل الاسم.
    pair_locked = throttled and AxesProxyHandler.is_locked(request, {"username": username})
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_staff:
        if throttled and not pair_locked:
            _count_failure(failures_key)
        if slowed:
            raise SignInError(429, NAME_LOCKED)
        raise SignInError(401, "اسم المستخدم أو كلمة المرور غير صحيحة")
    if throttled:
        # ح2: دخول صاحب الحساب يصفّر ما عُدّ على هذا الجهاز أو على الاسم، فلا يُحجب بعد خطأ واحد لاحق.
        cache.delete_many([failures_key, _slow_slot_key(failures_key)])
    login(request, user)
    record_audit(action="auth.login", actor=user, target=f"user:{user.pk}")
    return user


def remember_device(request: HttpRequest, user: AbstractBaseUser) -> str:
    """قيمة كوكي الجهاز بعد دخول ناجح. الجهاز المعروف يبقى بمعرّفه (وعدّاد فشله) ويتجدّد توقيعه."""
    device = _known_device(request, user.get_username()) or secrets.token_urlsafe(16)
    return signing.dumps({"n": _name_digest(user.get_username()), "d": device}, salt=_DEVICE_SALT)


def _known_device(request: HttpRequest, username: str) -> str | None:
    """معرّف الجهاز إن حمل كوكيًا موقَّعًا صالحًا لهذا الاسم نفسه، وإلا None."""
    raw = request.COOKIES.get(DEVICE_COOKIE, "")
    if not raw:
        return None
    try:
        value = signing.loads(raw, salt=_DEVICE_SALT, max_age=DEVICE_MAX_AGE_S)
    except signing.BadSignature:  # يشمل SignatureExpired
        return None
    if not isinstance(value, dict) or value.get("n") != _name_digest(username):
        return None
    device = value.get("d")
    return device if isinstance(device, str) and device else None


def _name_digest(username: str) -> str:
    # بصمة لا الاسم نفسه: مفتاح الذاكرة المؤقتة والكوكي بطول ثابت ولا يحملان ما كتبه الزائر.
    return hashlib.sha256(username.strip().casefold().encode()).hexdigest()


def _name_failures_key(username: str) -> str:
    return f"signin-failures:{_name_digest(username)}"


def _device_failures_key(device: str) -> str:
    return f"signin-failures:device:{hashlib.sha256(device.encode()).hexdigest()}"


def _slow_slot_key(failures_key: str) -> str:
    return f"{failures_key}:slot"


def _count_failure(key: str) -> None:
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
