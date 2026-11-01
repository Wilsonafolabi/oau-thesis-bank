from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def health_check(request):
    """Lightweight liveness endpoint for container/monitor probes."""
    return JsonResponse({"status": "ok", "service": "oau-thesis-bank-backend"}, status=200)


urlpatterns = [
    path("health", health_check),
    path("health/", health_check),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/theses/", include("theses.urls")),
    path("api/search/", include("search.urls")),
    path("api/researchers/", include("researchers.urls")),
    path("api/collaboration/", include("collaboration.urls")),
    path("api/messages/", include("messaging.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("api/admin/", include("admin_panel.urls")),
    # Authenticated, Django-mediated AI routes (service-to-service auth to V2).
    path("api/ai/", include("ai_integration.urls")),

    # OpenAPI docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
