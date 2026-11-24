from django.db.models import Sum
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import HasBotToken

from .models import Payment, Plan, ReferralReward, SubscriptionDevice
from .services import (
    BillingError,
    create_platega_or_stub_payment,
    finalize_paid_payment,
    format_iso_utc,
    get_active_subscription,
    serialize_plan,
    serialize_subscription,
    sync_payment_status_with_provider,
)


class BotPaymentCreateSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(min_value=1)
    plan_id = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=["balance", "external"], default="external")
    payment_method = serializers.ChoiceField(choices=["sbp", "crypto"], default="sbp")
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, default="")


class BotProfileView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request, telegram_id: int):
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

        referrals_count = User.objects.filter(referred_by=user).count()
        bonus_hours = (
            ReferralReward.objects.filter(referrer=user).aggregate(total=Sum("bonus_hours"))[
                "total"
            ]
            or 0
        )
        active_sub = get_active_subscription(user)

        return Response(
            {
                "telegram_id": user.telegram_id,
                "telegram_username": user.telegram_username,
                "email": user.email,
                "referral_code": user.referral_code,
                "balance_kopeks": 0,
                "has_used_trial": user.has_used_trial,
                "is_legal_accepted": user.is_legal_accepted,
                "legal_accepted_at": (
                    format_iso_utc(user.legal_accepted_at) if user.legal_accepted_at else None
                ),
                "referrals_count": referrals_count,
                "referral_bonus_hours": bonus_hours,
                "referral_bonus_kopeks": 0,
                "active_subscription": serialize_subscription(active_sub) if active_sub else None,
            },
            status=status.HTTP_200_OK,
        )


class BotPlanListView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by("sort_order", "price_kopeks", "id")
        return Response([serialize_plan(p) for p in plans], status=status.HTTP_200_OK)


class BotPlanDetailView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request, plan_id: int):
        plan = Plan.objects.filter(id=plan_id, is_active=True).first()
        if plan is None:
            return Response({"detail": "Тариф не найден"}, status=status.HTTP_404_NOT_FOUND)
        return Response(serialize_plan(plan), status=status.HTTP_200_OK)


class BotPaymentCreateView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request):
        serializer = BotPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["method"] == "balance":
            return Response(
                {"detail": "Оплата с баланса отключена. Используйте СБП или криптовалюту."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        telegram_id = serializer.validated_data["telegram_id"]
        plan_id = serializer.validated_data["plan_id"]
        payment_channel = serializer.validated_data["payment_method"]
        email = (serializer.validated_data.get("email") or "").strip()

        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

        try:
            payment = create_platega_or_stub_payment(
                user=user,
                plan_id=plan_id,
                payment_channel=payment_channel,
                email=email,
            )
            return Response(
                {
                    "status": payment.status,
                    "payment_id": payment.payment_id,
                    "payment_url": payment.payment_url or None,
                    "message": None,
                    "subscription": None,
                },
                status=status.HTTP_200_OK,
            )
        except BillingError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)


class BotPaymentStatusView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request, payment_id: str):
        payment = (
            Payment.objects.select_related("subscription", "subscription__plan")
            .filter(payment_id=payment_id)
            .first()
        )
        if payment is None:
            return Response({"detail": "Платеж не найден"}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == Payment.Status.PENDING:
            payment = sync_payment_status_with_provider(payment)
        elif payment.status == Payment.Status.PAID and payment.subscription is None:
            try:
                payment = finalize_paid_payment(payment.payment_id)
            except BillingError as exc:
                return Response({"detail": str(exc)}, status=exc.status_code)

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
                "message": None,
                "subscription": sub_payload,
            },
            status=status.HTTP_200_OK,
        )


class BotSubscriptionView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request, telegram_id: int):
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

        sub = get_active_subscription(user)
        if sub is None:
            return Response(
                {"detail": "Активная подписка не найдена"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_subscription(sub), status=status.HTTP_200_OK)


class BotDeviceListView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def get(self, request, telegram_id: int):
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

        sub = get_active_subscription(user)
        if sub is None:
            return Response([], status=status.HTTP_200_OK)

        devices = sub.devices.order_by("-last_seen_at")
        payload = [
            {
                "id": d.id,
                "hwid": d.hwid,
                "os": d.device_os,
                "is_blocked": d.is_blocked,
                "last_seen_at": format_iso_utc(d.last_seen_at),
            }
            for d in devices
        ]
        return Response(payload, status=status.HTTP_200_OK)


class BotDeviceResetView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request, telegram_id: int):
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response({"detail": "Пользователь не найден"}, status=status.HTTP_404_NOT_FOUND)

        sub = get_active_subscription(user)
        if sub is None:
            return Response(
                {"deleted_count": 0, "message": "Устройства сброшены"},
                status=status.HTTP_200_OK,
            )

        deleted_count, _ = sub.devices.all().delete()
        return Response(
            {"deleted_count": deleted_count, "message": "Устройства сброшены"},
            status=status.HTTP_200_OK,
        )


class BotDeviceDeleteView(APIView):
    authentication_classes = []
    permission_classes = [HasBotToken]

    def delete(self, request, telegram_id: int, device_id: int):
        device = SubscriptionDevice.objects.filter(
            id=device_id,
            subscription__user__telegram_id=telegram_id,
        ).first()
        if device is None:
            return Response({"detail": "Устройство не найдено"}, status=status.HTTP_404_NOT_FOUND)

        device.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)