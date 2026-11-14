from django.urls import include, path

urlpatterns = [
    path("", include("sub_gateway.urls")),
]
