import secrets

from django.conf import settings
from django.contrib.auth import login, logout
from django.core.cache import cache
from django.db import IntegrityError
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.services import get_active_subscription, serialize_subscription

from .models import User
from .permissions import HasBotToken
from .serializers import (
    BotAcceptLegalSerializer,
    BotGetOrCreateUserSerializer,
    TelegramAuthConfirmSerializer,
    TelegramAuthInitSerializer,
)

TG_AUTH_CACHE_PREFIX = "tg_auth:"


def _iso_utc(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _serialize_web_user(user: User) -> dict:
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "telegram_username": user.telegram_username,
        "referral_code": user.referral_code,
        "balance_kopeks": user.balance_kopeks,
        "is_legal_accepted": user.is_legal_accepted,
        "legal_accepted_at": _iso_utc(user.legal_accepted_at),
    }


class BotGetOrCreateUserView(APIView):
    """
    Ищет пользователя по telegram_id или создает нового в БД Django с единым xray_uuid.
    На панели 3x-ui пользователь при регистрации НЕ создается — только при появлении подписки.
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


class TelegramAuthInitView(APIView):
    """
    Публичный эндпоинт для фронта: создает одноразовый auth_token в Redis
    и возвращает ссылку на Telegram-бота ?start=auth_<token>.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TelegramAuthInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        accepted_legal = serializer.validated_data["accepted_legal"]
        auth_token = secrets.token_urlsafe(24)
        ttl = settings.TELEGRAM_AUTH_TTL_SECONDS

        cache.set(
            f"{TG_AUTH_CACHE_PREFIX}{auth_token}",
            {
                "status": "pending",
                "telegram_id": None,
                "user_id": None,
                "accepted_legal": accepted_legal,
            },
            timeout=ttl,
        )

        return Response(
            {
                "auth_token": auth_token,
                "bot_url": f"https://t.me/{settings.BOT_USERNAME}?start=auth_{auth_token}",
                "expires_in": ttl,
            },
            status=status.HTTP_200_OK,
        )


class TelegramAuthStatusView(APIView):
    """
    Публичный поллинг статуса входа с сайта.
    После подтверждения ботом выставляет Django session cookie (HttpOnly)
    и удаляет одноразовый auth_token из Redis.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, auth_token: str):
        cache_key = f"{TG_AUTH_CACHE_PREFIX}{auth_token}"
        data = cache.get(cache_key)
        if data is None:
            return Response(
                {"status": "expired", "detail": "Срок действия ссылки истек"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if data.get("status") != "confirmed":
            return Response({"status": "pending"}, status=status.HTTP_200_OK)

        cache.delete(cache_key)
        user = User.objects.filter(id=data.get("user_id")).first()
        if user is None:
            return Response(
                {"status": "expired", "detail": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        get_token(request)

        return Response(
            {
                "status": "confirmed",
                "user": _serialize_web_user(user),
            },
            status=status.HTTP_200_OK,
        )


class TelegramAuthConfirmView(APIView):
    """
    Закрытый эндпоинт для бота: подтверждает вход по auth_token
    и привязывает его к User по telegram_id.
    """

    authentication_classes = []
    permission_classes = [HasBotToken]

    def post(self, request):
        serializer = TelegramAuthConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_token = serializer.validated_data["auth_token"].strip()
        auth_token = raw_token[5:] if raw_token.startswith("auth_") else raw_token
        telegram_id = serializer.validated_data["telegram_id"]
        raw_username = (serializer.validated_data.get("telegram_username") or "").lstrip("@").strip()
        telegram_username = raw_username or str(telegram_id)

        cache_key = f"{TG_AUTH_CACHE_PREFIX}{auth_token}"
        data = cache.get(cache_key)
        if not isinstance(data, dict) or data.get("status") != "pending":
            return Response(
                {"detail": "Ссылка устарела или уже использована"},
                status=status.HTTP_404_NOT_FOUND,
            )

        accepted_legal = bool(data.get("accepted_legal"))
        now = timezone.now()

        try:
            user, _ = User.objects.get_or_create(
                telegram_id=telegram_id,
                defaults={
                    "username": f"tg_{telegram_id}",
                    "telegram_username": telegram_username,
                    "is_legal_accepted": accepted_legal,
                    "legal_accepted_at": now if accepted_legal else None,
                },
            )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)

        update_fields: list[str] = []
        if user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            update_fields.append("telegram_username")
        if accepted_legal and not user.is_legal_accepted:
            user.is_legal_accepted = True
            user.legal_accepted_at = now
            update_fields.extend(["is_legal_accepted", "legal_accepted_at"])
        if update_fields:
            user.save(update_fields=update_fields)

        cache.set(
            cache_key,
            {
                "status": "confirmed",
                "user_id": user.id,
                "telegram_id": user.telegram_id,
            },
            timeout=60,
        )

        return Response(
            {"status": "confirmed", "message": "Вход на сайт подтвержден"},
            status=status.HTTP_200_OK,
        )


class WebMeView(APIView):
    """Текущий авторизованный пользователь сайта + активная подписка."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        get_token(request)
        user = request.user
        sub = get_active_subscription(user)
        referrals_count = User.objects.filter(referred_by=user).count()

        return Response(
            {
                "user": _serialize_web_user(user),
                "referrals_count": referrals_count,
                "active_subscription": serialize_subscription(sub) if sub else None,
                "devices_count": sub.devices.count() if sub else 0,
            },
            status=status.HTTP_200_OK,
        )


class WebLogoutView(APIView):
    """Выход из веб-сессии."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)