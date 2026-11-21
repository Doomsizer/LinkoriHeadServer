from django.urls import path

from .views import SubscriptionGatewayView, SubscriptionOpenAppView

urlpatterns = [
    path(
        "<str:sub_token>/lte/open/<str:app_name>",
        SubscriptionOpenAppView.as_view(network_type="lte"),
        name="subscription-lte-open-app",
    ),
    path(
        "<str:sub_token>/lte/open/<str:app_name>/",
        SubscriptionOpenAppView.as_view(network_type="lte"),
        name="subscription-lte-open-app-slash",
    ),
    path(
        "<str:sub_token>/wifi/open/<str:app_name>",
        SubscriptionOpenAppView.as_view(network_type="wifi"),
        name="subscription-wifi-open-app",
    ),
    path(
        "<str:sub_token>/wifi/open/<str:app_name>/",
        SubscriptionOpenAppView.as_view(network_type="wifi"),
        name="subscription-wifi-open-app-slash",
    ),
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
    path(
        "<str:sub_token>/lte",
        SubscriptionGatewayView.as_view(network_type="lte"),
        name="subscription-gateway-lte",
    ),
    path(
        "<str:sub_token>/lte/",
        SubscriptionGatewayView.as_view(network_type="lte"),
        name="subscription-gateway-lte-slash",
    ),
    path(
        "<str:sub_token>/wifi",
        SubscriptionGatewayView.as_view(network_type="wifi"),
        name="subscription-gateway-wifi",
    ),
    path(
        "<str:sub_token>/wifi/",
        SubscriptionGatewayView.as_view(network_type="wifi"),
        name="subscription-gateway-wifi-slash",
    ),
    path("<str:sub_token>", SubscriptionGatewayView.as_view(), name="subscription-gateway"),
    path("<str:sub_token>/", SubscriptionGatewayView.as_view(), name="subscription-gateway-slash"),
]