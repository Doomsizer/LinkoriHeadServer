from django.urls import path

from .views import BotAcceptLegalView, BotGetOrCreateUserView

urlpatterns = [
    path("get-or-create/", BotGetOrCreateUserView.as_view(), name="bot-get-or-create-user"),
    path("accept-legal/", BotAcceptLegalView.as_view(), name="bot-accept-legal"),
]