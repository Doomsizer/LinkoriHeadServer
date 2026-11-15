from django.urls import path

from .views import BotGetOrCreateUserView

urlpatterns = [
    path("get-or-create/", BotGetOrCreateUserView.as_view(), name="bot-get-or-create-user"),
]