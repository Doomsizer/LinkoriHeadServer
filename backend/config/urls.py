from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", healthcheck, name="api-health"),
    path("api/accounts/", include("accounts.urls")),
    path("api/bot/", include("billing.bot_urls")),
    path("api/billing/", include("billing.urls")),
    path("api/probes/", include("probes.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("sub/", include("sub_gateway.urls")),
    ]