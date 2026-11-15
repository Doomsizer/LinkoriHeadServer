from django.urls import path

from .bot_views import (
    BotDeviceDeleteView,
    BotDeviceListView,
    BotDeviceResetView,
    BotPaymentCreateView,
    BotPaymentStatusView,
    BotPlanDetailView,
    BotPlanListView,
    BotProfileView,
    BotSubscriptionView,
)

urlpatterns = [
    path("profile/<int:telegram_id>/", BotProfileView.as_view(), name="bot-profile"),
    path("plans/", BotPlanListView.as_view(), name="bot-plans"),
    path("plans/<int:plan_id>/", BotPlanDetailView.as_view(), name="bot-plan-detail"),
    path("payments/create/", BotPaymentCreateView.as_view(), name="bot-payment-create"),
    path(
        "payments/<str:payment_id>/status/",
        BotPaymentStatusView.as_view(),
        name="bot-payment-status",
    ),
    path(
        "subscription/<int:telegram_id>/",
        BotSubscriptionView.as_view(),
        name="bot-subscription",
    ),
    path("devices/<int:telegram_id>/", BotDeviceListView.as_view(), name="bot-devices"),
    path(
        "devices/<int:telegram_id>/reset/",
        BotDeviceResetView.as_view(),
        name="bot-devices-reset",
    ),
    path(
        "devices/<int:telegram_id>/<int:device_id>/",
        BotDeviceDeleteView.as_view(),
        name="bot-device-delete",
    ),
]