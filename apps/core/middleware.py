"""ترويسة Content-Security-Policy من الإعداد `CONTENT_SECURITY_POLICY` (فارغ = معطَّلة)."""

from __future__ import annotations

from django.conf import settings

# صفحة وثائق API (للمشرفين) تحمّل Swagger من CDN وبسكربت مضمَّن؛ تُستثنى بدل إرخاء السياسة للجميع.
_EXEMPT_PREFIX = "/api/docs"


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = settings.CONTENT_SECURITY_POLICY
        if policy and not request.path.startswith(_EXEMPT_PREFIX):
            response.headers.setdefault("Content-Security-Policy", policy)
        return response
