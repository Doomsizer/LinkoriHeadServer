from django.urls import path

from .views import SubscriptionGatewayView

urlpatterns = [
    path("<str:sub_token>", SubscriptionGatewayView.as_view(), name="subscription-gateway"),
    path("<str:sub_token>/", SubscriptionGatewayView.as_view(), name="subscription-gateway-slash"),
]
