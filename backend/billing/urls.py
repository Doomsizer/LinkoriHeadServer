# backend/billing/urls.py
from django.urls import path

from .views import MockPaymentView

urlpatterns = [
    path("mock-pay/<str:payment_id>/", MockPaymentView.as_view(), name="billing-mock-pay"),
]