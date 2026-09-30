import json
import os
import urllib.request
import urllib.error
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# ---------------------------------------------------------
# AI INTELLIGENCE PROXY & HEALTH CHECK (WITH LOGGING)
# ---------------------------------------------------------
@csrf_exempt
def ai_health_check(request):
    print(f"\n🔥 [AI LOG] Health check requested: {request.method} {request.path}")
    return JsonResponse({
        'status': 'connected', 
        'service': 'AI Intelligence Layer',
        'endpoints': ['rag-query', 'check-similarity', 'extract-metadata', 'graphs']
    }, status=200)

@csrf_exempt
def ai_proxy(request, path):
    print(f"\n🔥 [AI LOG] Proxy requested: {request.method} {request.path} | Target path: {path}")
    
    ai_url = os.getenv('AI_INTELLIGENCE_URL', 'http://host.docker.internal:8888')
    target_url = f"{ai_url}/api/v1/ai/{path}"
    print(f"🔥 [AI LOG] Forwarding to: {target_url}")
    
    try:
        headers = {}
        content_type = request.META.get('CONTENT_TYPE')
        if content_type:
            headers['Content-Type'] = content_type
            
        auth = request.META.get('HTTP_AUTHORIZATION')
        if auth:
            headers['Authorization'] = auth
            
        data = request.body if request.body else None
        req = urllib.request.Request(target_url, data=data, headers=headers, method=request.method)
        
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode())
            print(f"✅ [AI LOG] Success! Status: {response.status}")
            return JsonResponse(response_data, status=response.status)
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"❌ [AI LOG] HTTP Error {e.code}: {error_body}")
        return JsonResponse({'error': 'AI Service Error', 'detail': error_body, 'status': e.code}, status=e.code)
    except Exception as e:
        print(f"❌ [AI LOG] Exception: {str(e)}")
        return JsonResponse({'error': 'AI Service Unavailable', 'detail': str(e)}, status=502)
# ---------------------------------------------------------


urlpatterns = [
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
    
    # --- AI ROUTES ---
    path("api/ai/", ai_health_check),          
    path("api/ai/<path:path>", ai_proxy),      
    
    # OpenAPI docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)