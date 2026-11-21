"""المسارات: API تحت /api/، الصحة تحت /health/، والوسائط للمشرفين تحت /media/، وكل ما عدا ذلك يذهب إلى واجهة Vue (SPA)."""

from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path

from apps.capacity.api import router as capacity_router
from apps.catalog.api import router as catalog_router
from apps.core.api import api
from apps.core.views import health, media_file, robots_txt, spa
from apps.orders.api import router as orders_router
from apps.production.api import router as production_router

api.add_router("/capacity", capacity_router)
api.add_router("/catalog", catalog_router)
api.add_router("/orders", orders_router)
api.add_router("/production", production_router)

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", api.urls),
    path("health/", health, name="health"),
    path("robots.txt", robots_txt, name="robots"),
    # في التطوير والإنتاج معًا: whitenoise يخدم static وحده، وMEDIA_URL ثابت على /media/.
    path("media/<path:path>", media_file, name="media"),
    re_path(r"^(?!api/|static/|media/).*$", spa, name="spa"),
]
