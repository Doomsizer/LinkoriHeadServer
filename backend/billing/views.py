import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sub_gateway.views import get_client_ip

from .legal_docs import get_legal_documents_payload
from .models import Payment, Plan
from .platega import verify_platega_headers
from .services import (
    MAX_TRANSACTION_KOPEKS,
    BillingError,
    create_platega_or_stub_payment,
    finalize_paid_payment,
    serialize_plan,
    serialize_subscription,
    sync_payment_status_with_provider,
)

logger = logging.getLogger(__name__)


class WebCheckoutCreateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1)
    payment_method = serializers.ChoiceField(choices=["sbp", "crypto"], default="sbp")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class PublicPlanListView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(
            is_active=True,
            price_kopeks__lte=MAX_TRANSACTION_KOPEKS,
        ).order_by("sort_order", "price_kopeks", "id")
        return Response([serialize_plan(p) for p in plans], status=status.HTTP_200_OK)


class PublicLegalDocsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_legal_documents_payload(), status=status.HTTP_200_OK)


class WebCheckoutCreateView(APIView):
    """Создает реальную транзакцию в Platega для авторизованного на сайте пользователя."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WebCheckoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_id = serializer.validated_data["plan_id"]
        payment_channel = serializer.validated_data["payment_method"]
        email = serializer.validated_data["email"]
        client_ip = get_client_ip(request)

        try:
            payment = create_platega_or_stub_payment(
                user=request.user,
                plan_id=plan_id,
                payment_channel=payment_channel,
                email=email,
                client_ip=client_ip,
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        return Response(
            {
                "status": payment.status,
                "payment_id": payment.payment_id,
                "payment_url": payment.payment_url,
            },
            status=status.HTTP_200_OK,
        )


class WebPaymentStatusView(APIView):
    """Проверяет статус платежа в БД (и запрашивает Platega, если еще pending)."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id: str):
        payment = (
            Payment.objects.select_related("subscription", "subscription__plan")
            .filter(payment_id=payment_id, user=request.user)
            .first()
        )
        if payment is None:
            return Response({"detail": "Платеж не найден"}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == Payment.Status.PENDING:
            payment = sync_payment_status_with_provider(payment)

        sub_payload = (
            serialize_subscription(payment.subscription)
            if payment.status == Payment.Status.PAID and payment.subscription is not None
            else None
        )
        return Response(
            {
                "status": payment.status,
                "payment_id": payment.payment_id,
                "payment_url": payment.payment_url if payment.status == Payment.Status.PENDING else None,
                "subscription": sub_payload,
            },
            status=status.HTTP_200_OK,
        )


class PlategaWebhookView(APIView):
    """
    Принимает webhook-колбэки от Platega.io.
    Подлинность проверяется по заголовкам X-MerchantId и X-Secret.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_platega_headers(request.headers):
            logger.warning("Отклонен webhook Platega: неверные X-MerchantId / X-Secret")
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}
        tx_id = str(data.get("id") or "").strip()
        tx_status = str(data.get("status") or "").upper().strip()
        payload_id = str(data.get("payload") or "").strip()

        payment = None
        if tx_id:
            payment = Payment.objects.filter(external_id=tx_id).first()
        if payment is None and payload_id:
            payment = Payment.objects.filter(payment_id=payload_id).first()

        if payment is None:
            logger.warning("Webhook Platega для неизвестного платежа id=%s payload=%s", tx_id, payload_id)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        if tx_status == "CONFIRMED":
            try:
                finalize_paid_payment(payment.payment_id)
            except BillingError as exc:
                logger.error("Ошибка финализации платежа %s: %s", payment.payment_id, exc)
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        elif tx_status in ("CANCELED", "CHARGEBACKED"):
            if payment.status == Payment.Status.PENDING:
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class MockPaymentView(View):
    def _is_enabled(self) -> bool:
        return settings.PAYMENT_PROVIDER == "stub" and settings.ALLOW_STUB_PAYMENTS

    def get(self, request, payment_id: str):
        if not self._is_enabled():
            return HttpResponse("Тестовые платежи отключены", status=404)

        payment = Payment.objects.select_related("plan").filter(payment_id=payment_id).first()
        if payment is None:
            return HttpResponse("Платеж не найден", status=404)

        amount_rub = payment.amount_kopeks / 100
        if payment.status == Payment.Status.PAID:
            body = "<h1>Оплата уже подтверждена</h1><p>Вернитесь в Telegram-бота.</p>"
        else:
            body = (
                f"<h1>Тестовая оплата Linkori</h1>"
                f"<p>Тариф: {payment.plan.name} — {amount_rub:.2f} руб.</p>"
                f'<form method="post"><button type="submit" '
                f'style="padding:12px 20px;font-size:16px;cursor:pointer;">'
                f"Подтвердить тестовую оплату</button></form>"
            )
        return HttpResponse(
            f"<!DOCTYPE html><html lang='ru'><meta charset='utf-8'><body>{body}</body></html>"
        )

    def post(self, request, payment_id: str):
        if not self._is_enabled():
            return HttpResponse("Тестовые платежи отключены", status=404)
        try:
            finalize_paid_payment(payment_id)
        except BillingError as exc:
            return HttpResponse(str(exc), status=exc.status_code)

        return HttpResponse(
            "<!DOCTYPE html><html lang='ru'><meta charset='utf-8'><body>"
            "<h1>Оплата прошла успешно!</h1>"
            "<p>Вернитесь в Telegram-бота @linkoribot и нажмите кнопку проверки оплаты.</p>"
            "</body></html>"
        )