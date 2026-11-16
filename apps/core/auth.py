"""مصادقة API: جلسة Django مع CSRF، وللمشرفين فقط (RBAC بسيط حتى تُعرَّف الأدوار)."""

from __future__ import annotations

from django.http import HttpRequest
from ninja.security import SessionAuth


class StaffSessionAuth(SessionAuth):
    def authenticate(self, request: HttpRequest, key: str | None):
        user = request.user
        if user.is_authenticated and user.is_staff:
            return user
        return None


staff_auth = StaffSessionAuth()


def request_id(request: HttpRequest) -> str:
    return request.headers.get("X-Request-ID", "")
