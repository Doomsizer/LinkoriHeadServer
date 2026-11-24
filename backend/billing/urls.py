from django.urls import path

from .views import (
    MockPaymentView,
    PlategaWebhookView,
    PublicLegalDocsView,
    PublicPlanListView,
    WebCheckoutCreateView,
    WebPaymentStatusView,
)

urlpatterns = [
    path("plans/", PublicPlanListView.as_view(), name="billing-public-plans"),
    path("legal/", PublicLegalDocsView.as_view(), name="billing-public-legal"),
    path("web/checkout/", WebCheckoutCreateView.as_view(), name="billing-web-checkout"),
    path(
        "web/payments/<str:payment_id>/status/",
        WebPaymentStatusView.as_view(),
        name="billing-web-payment-status",
    ),
    path("webhooks/platega/", PlategaWebhookView.as_view(), name="billing-platega-webhook"),
    path("mock-pay/<str:payment_id>/", MockPaymentView.as_view(), name="billing-mock-pay"),
]