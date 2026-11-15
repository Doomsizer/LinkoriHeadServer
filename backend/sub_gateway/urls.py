from django.urls import path

from .views import SubscriptionGatewayView, SubscriptionOpenAppView

urlpatterns = [
    path(
        "<str:sub_token>/open/<str:app_name>",
        SubscriptionOpenAppView.as_view(),
        name="subscription-open-app",
    ),
    path(
        "<str:sub_token>/open/<str:app_name>/",
        SubscriptionOpenAppView.as_view(),
        name="subscription-open-app-slash",
    ),
    path("<str:sub_token>", SubscriptionGatewayView.as_view(), name="subscription-gateway"),
    path("<str:sub_token>/", SubscriptionGatewayView.as_view(), name="subscription-gateway-slash"),
]