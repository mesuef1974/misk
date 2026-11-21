"""المسارات: API تحت /api/، الصحة تحت /health/، والوسائط للمشرفين تحت /media/، وكل ما عدا ذلك يذهب إلى واجهة Vue (SPA)."""

from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path

from apps.capacity.api import router as capacity_router
from apps.catalog.api import router as catalog_router
from apps.catalog.storefront_api import router as store_router
from apps.checkout.api import cart_router, payments_router
from apps.core.api import api
from apps.core.views import health, media_file, robots_txt, spa
from apps.fulfillment.api import staff_router as fulfillment_router
from apps.fulfillment.api import track_router, zones_router
from apps.orders.api import router as orders_router
from apps.production.api import router as production_router

api.add_router("/capacity", capacity_router)
api.add_router("/catalog", catalog_router)
api.add_router("/fulfillment", fulfillment_router)
api.add_router("/orders", orders_router)
api.add_router("/payments", payments_router)
api.add_router("/production", production_router)
api.add_router("/store", store_router)
api.add_router("/store/cart", cart_router)
api.add_router("/store/delivery-zones", zones_router)
api.add_router("/store/track", track_router)

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", api.urls),
    path("health/", health, name="health"),
    path("robots.txt", robots_txt, name="robots"),
    # في التطوير والإنتاج معًا: whitenoise يخدم static وحده، وMEDIA_URL ثابت على /media/.
    path("media/<path:path>", media_file, name="media"),
    re_path(r"^(?!api/|static/|media/).*$", spa, name="spa"),
]
