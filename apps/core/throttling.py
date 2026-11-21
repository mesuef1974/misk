"""تحديد معدل المسارات العامة بعنوان العميل المحسوب من الوكلاء الموثوقين (`client_ip`).

مخنق Ninja الافتراضي يقرأ X-Forwarded-For بإعداده هو؛ هنا المصدر نفسه الذي يُقفل عليه الدخول،
فلا يتجاوز العميل الحدّ بترويسة يكتبها. العدّاد في الذاكرة المؤقتة (Redis في الإنتاج فيُشارَك بين العمّال).
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja.throttling import SimpleRateThrottle

from .auth import client_ip


class ClientRateThrottle(SimpleRateThrottle):
    """`scope` يفصل عدّاد كل مجموعة مسارات، و`rate` بصيغة Ninja: «30/m»."""

    def __init__(self, scope: str, rate: str):
        self.scope = scope
        super().__init__(rate)

    def get_cache_key(self, request: HttpRequest) -> str:
        return self.cache_format % {"scope": self.scope, "ident": client_ip(request) or "unknown"}
