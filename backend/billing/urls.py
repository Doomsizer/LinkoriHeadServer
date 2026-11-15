from django.urls import path

from .views import (
    MockPaymentView,
    PublicCheckoutStubView,
    PublicLegalDocsView,
    PublicPlanListView,
)

urlpatterns = [
    path("plans/", PublicPlanListView.as_view(), name="billing-public-plans"),
    path("legal/", PublicLegalDocsView.as_view(), name="billing-public-legal"),
    path("checkout-preview/", PublicCheckoutStubView.as_view(), name="billing-checkout-preview"),
    path("mock-pay/<str:payment_id>/", MockPaymentView.as_view(), name="billing-mock-pay"),
]