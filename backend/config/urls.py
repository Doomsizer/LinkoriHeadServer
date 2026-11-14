from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", healthcheck, name="api-health"),
    path("api/probes/", include("probes.urls")),
]

# В режиме разработки можно тестировать шлюз подписок через /sub/{token}
if settings.DEBUG:
    urlpatterns += [
        path("sub/", include("sub_gateway.urls")),
    ]
