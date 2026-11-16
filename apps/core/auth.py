"""مصادقة API: جلسة Django مع CSRF، وللمشرفين فقط (RBAC بسيط حتى تُعرَّف الأدوار)."""

from __future__ import annotations

import ipaddress

from django.conf import settings
from django.http import HttpRequest
from ninja.security import SessionAuth


class StaffSessionAuth(SessionAuth):
    def authenticate(self, request: HttpRequest, key: str | None):
        user = request.user
        if user.is_authenticated and user.is_staff:
            return user
        return None


staff_auth = StaffSessionAuth()


def client_ip(request: HttpRequest) -> str | None:
    """عنوان العميل لقفل الدخول (`AXES_CLIENT_IP_CALLABLE`).

    كل وكيل موثوق يُلحق بـ X-Forwarded-For عنوان من اتصل به، فالعنوان الذي كتبه أبعد وكيل موثوق هو
    الخانة رقم `TRUSTED_PROXY_COUNT` من اليمين؛ ما قبلها يكتبه العميل نفسه ولا يُصدَّق.
    بلا وكلاء موثوقين، أو بترويسة أقصر من العدد أو غير صالحة، يُؤخذ `REMOTE_ADDR`.
    """
    remote = request.META.get("REMOTE_ADDR")
    count = settings.TRUSTED_PROXY_COUNT
    if count < 1:
        return remote
    hops = [hop.strip() for hop in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if hop.strip()]
    if len(hops) < count:
        return remote
    try:
        return str(ipaddress.ip_address(hops[-count]))
    except ValueError:
        return remote


def request_id(request: HttpRequest) -> str:
    return request.headers.get("X-Request-ID", "")
