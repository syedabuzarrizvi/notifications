from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def api_root(request):
    return JsonResponse({
        "message": "Techrar Notification Platform API",
        "version": "1.0",
        "endpoints": {
            "auth": "/api/auth/",
            "notifications": "/api/notifications/",
            "campaigns": "/api/campaigns/",
            "templates": "/api/templates/",
            "recipients": "/api/recipients/"
        }
    })

urlpatterns = [
    path('', api_root, name='api_root'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/campaigns/', include('campaigns.urls')),
    path('api/templates/', include('templates.urls')),
    path('api/recipients/', include('recipients.urls')),
]
