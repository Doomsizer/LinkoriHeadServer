from django.urls import path

from .views import (
    BotAcceptLegalView,
    BotGetOrCreateUserView,
    TelegramAuthConfirmView,
    TelegramAuthInitView,
    TelegramAuthStatusView,
    WebLogoutView,
    WebMeView,
)

urlpatterns = [
    path("get-or-create/", BotGetOrCreateUserView.as_view(), name="bot-get-or-create-user"),
    path("accept-legal/", BotAcceptLegalView.as_view(), name="bot-accept-legal"),
    path("telegram-auth/init/", TelegramAuthInitView.as_view(), name="tg-auth-init"),
    path(
        "telegram-auth/status/<str:auth_token>/",
        TelegramAuthStatusView.as_view(),
        name="tg-auth-status",
    ),
    path("telegram-auth/confirm/", TelegramAuthConfirmView.as_view(), name="tg-auth-confirm"),
    path("me/", WebMeView.as_view(), name="web-me"),
    path("logout/", WebLogoutView.as_view(), name="web-logout"),
]