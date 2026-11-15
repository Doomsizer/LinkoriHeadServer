# backend/billing/views.py
from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Payment
from .services import BillingError, finalize_paid_payment


@method_decorator(csrf_exempt, name="dispatch")
class MockPaymentView(View):
    """
    Тестовая страница подтверждения внешнего платежа при PAYMENT_PROVIDER=stub.
    Отключается автоматически при переключении PAYMENT_PROVIDER или ALLOW_STUB_PAYMENTS=0.
    """

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
            "<p>Вернитесь в Telegram-бота и нажмите кнопку проверки оплаты.</p>"
            "</body></html>"
        )