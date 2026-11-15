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
    Ищет пользователя по telegram_id или создает нового с единым xray_uuid
    и при необходимости заводит его на всех активных панелях 3x-ui.
    """

    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request):
        serializer = BotGetOrCreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        telegram_id = serializer.validated_data["telegram_id"]
        telegram_username = serializer.validated_data["telegram_username"].lstrip("@").strip()
        sync_panels = serializer.validated_data["sync_panels"]

        try:
            user, created = User.objects.get_or_create(
                telegram_id=telegram_id,
                defaults={
                    "username": f"tg_{telegram_id}",
                    "telegram_username": telegram_username,
                },
            )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)
            created = False

        if telegram_username and user.telegram_username != telegram_username:
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