from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nodes.xui_sync import ensure_user_on_all_panels

from .models import User
from .permissions import HasBotToken
from .serializers import BotAcceptLegalSerializer, BotGetOrCreateUserSerializer


def _iso_utc(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


class BotGetOrCreateUserView(APIView):
    """
    Ищет пользователя по telegram_id или создает нового с единым xray_uuid,
    привязывает пригласившего по referred_by_code (при создании) и заводит
    клиента на активных панелях 3x-ui.
    """

    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request):
        serializer = BotGetOrCreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telegram_id = serializer.validated_data["telegram_id"]
        raw_username = (serializer.validated_data.get("telegram_username") or "").lstrip("@").strip()
        telegram_username = raw_username or str(telegram_id)
        ref_code = (serializer.validated_data.get("referred_by_code") or "").strip()
        is_legal_accepted = serializer.validated_data["is_legal_accepted"]
        sync_panels = serializer.validated_data["sync_panels"]

        referrer = None
        if ref_code:
            candidate = User.objects.filter(referral_code__iexact=ref_code).first()
            if candidate is not None and candidate.telegram_id != telegram_id:
                referrer = candidate

        now = timezone.now()
        try:
            user, created = User.objects.get_or_create(
                telegram_id=telegram_id,
                defaults={
                    "username": f"tg_{telegram_id}",
                    "telegram_username": telegram_username,
                    "referred_by": referrer,
                    "is_legal_accepted": is_legal_accepted,
                    "legal_accepted_at": now if is_legal_accepted else None,
                },
            )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)
            created = False

        update_fields: list[str] = []
        if user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            update_fields.append("telegram_username")
        if is_legal_accepted and not user.is_legal_accepted:
            user.is_legal_accepted = True
            user.legal_accepted_at = now
            update_fields.extend(["is_legal_accepted", "legal_accepted_at"])
        if update_fields:
            user.save(update_fields=update_fields)

        panels_info = None
        if sync_panels:
            panels_info = ensure_user_on_all_panels(user)

        return Response(
            {
                "created": created,
                "user": {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "telegram_username": user.telegram_username,
                    "xray_uuid": str(user.xray_uuid),
                    "referral_code": user.referral_code,
                    "balance_kopeks": user.balance_kopeks,
                    "is_legal_accepted": user.is_legal_accepted,
                    "legal_accepted_at": _iso_utc(user.legal_accepted_at),
                },
                "panels": panels_info,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BotAcceptLegalView(APIView):
    """
    Фиксирует принятие пользователем Политики конфиденциальности,
    Пользовательского соглашения и cookies.
    """

    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request):
        serializer = BotAcceptLegalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telegram_id = serializer.validated_data["telegram_id"]
        accepted = serializer.validated_data["accepted"]
        if not accepted:
            return Response(
                {"detail": "Необходимо подтвердить согласие с документами"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            return Response(
                {"detail": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user.is_legal_accepted:
            user.is_legal_accepted = True
            user.legal_accepted_at = timezone.now()
            user.save(update_fields=["is_legal_accepted", "legal_accepted_at"])

        return Response(
            {
                "telegram_id": user.telegram_id,
                "is_legal_accepted": user.is_legal_accepted,
                "legal_accepted_at": _iso_utc(user.legal_accepted_at),
            },
            status=status.HTTP_200_OK,
        )