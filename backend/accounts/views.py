from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nodes.xui_sync import ensure_user_on_all_panels

from .models import User
from .permissions import HasBotToken
from .serializers import BotGetOrCreateUserSerializer


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
        sync_panels = serializer.validated_data["sync_panels"]

        referrer = None
        if ref_code:
            candidate = User.objects.filter(referral_code__iexact=ref_code).first()
            if candidate is not None and candidate.telegram_id != telegram_id:
                referrer = candidate

        try:
            user, created = User.objects.get_or_create(
                telegram_id=telegram_id,
                defaults={
                    "username": f"tg_{telegram_id}",
                    "telegram_username": telegram_username,
                    "referred_by": referrer,
                },
            )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)
            created = False

        if user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            user.save(update_fields=["telegram_username"])

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
                },
                "panels": panels_info,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )