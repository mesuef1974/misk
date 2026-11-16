"""المسارات: API تحت /api/، الصحة تحت /health/، وكل ما عدا ذلك يذهب إلى واجهة Vue (SPA)."""

from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path

from apps.catalog.api import router as catalog_router
from apps.core.api import api
from apps.core.views import health, spa
from apps.orders.api import router as orders_router
from apps.production.api import router as production_router

api.add_router("/catalog", catalog_router)
api.add_router("/orders", orders_router)
api.add_router("/production", production_router)

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", api.urls),
    path("health/", health, name="health"),
    re_path(r"^(?!api/|static/|media/).*$", spa, name="spa"),
]
