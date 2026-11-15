from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .legal_docs import get_legal_documents_payload
from .models import Payment, Plan
from .services import (
    MAX_TRANSACTION_KOPEKS,
    BillingError,
    finalize_paid_payment,
    serialize_plan,
)


class PublicCheckoutPreviewSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1)
    email = serializers.EmailField()
    accepted_terms = serializers.BooleanField()

    def validate_accepted_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                "Необходимо принять Пользовательское соглашение и Политику конфиденциальности."
            )
        return value


class PublicPlanListView(APIView):
    """Публичная витрина тарифов для сайта (только активные и до 10 000 руб.)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(
            is_active=True,
            price_kopeks__lte=MAX_TRANSACTION_KOPEKS,
        ).order_by("sort_order", "price_kopeks", "id")
        return Response([serialize_plan(p) for p in plans], status=status.HTTP_200_OK)


class PublicLegalDocsView(APIView):
    """Отдает Политику конфиденциальности и Пользовательское соглашение для сайта и бота."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_legal_documents_payload(), status=status.HTTP_200_OK)


class PublicCheckoutStubView(APIView):
    """
    Проверяет обязательный email, согласие с документами и лимит 10 000 руб.
    На этапе подключения кассы отдает временную заглушку о недоступности оплаты.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PublicCheckoutPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_id = serializer.validated_data["plan_id"]
        email = serializer.validated_data["email"]
        plan = Plan.objects.filter(id=plan_id, is_active=True).first()
        if plan is None:
            return Response({"detail": "Выбранный тариф не найден"}, status=status.HTTP_404_NOT_FOUND)
        if plan.price_kopeks > MAX_TRANSACTION_KOPEKS:
            return Response(
                {"detail": "Сумма одной транзакции не может превышать 10 000 руб."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "unavailable",
                "plan": serialize_plan(plan),
                "email": email,
                "message": (
                    "Оплата временно недоступна: платежная система проходит финальное "
                    "подключение. Пожалуйста, попробуйте позже или напишите в поддержку "
                    "@Linkorisupport."
                ),
            },
            status=status.HTTP_200_OK,
        )


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