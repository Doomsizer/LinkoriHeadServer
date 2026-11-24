import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login, logout
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError
from django.db.models import Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import ReferralReward
from billing.services import get_active_subscription, serialize_subscription

from .email_utils import EmailValidationError, validate_email_domain
from .models import User
from .permissions import HasBotToken
from .serializers import (
    BotAcceptLegalSerializer,
    BotGetOrCreateUserSerializer,
    EmailOtpRequestSerializer,
    EmailOtpVerifySerializer,
    TelegramAuthConfirmSerializer,
    TelegramAuthInitSerializer,
    WebApplyReferralSerializer,
)
from .services import AccountLinkError, attach_or_merge_email, merge_users

TG_AUTH_CACHE_PREFIX = "tg_auth:"
EMAIL_OTP_PREFIX = "email_otp:"
EMAIL_OTP_COOLDOWN_PREFIX = "email_otp_cd:"
REFERRAL_WINDOW = timedelta(hours=24)


def _iso_utc(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _serialize_web_user(user: User) -> dict:
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "telegram_username": user.telegram_username,
        "email": user.email,
        "referral_code": user.referral_code,
        "balance_kopeks": 0,
        "has_used_trial": user.has_used_trial,
        "is_legal_accepted": user.is_legal_accepted,
        "legal_accepted_at": _iso_utc(user.legal_accepted_at),
    }


class BotGetOrCreateUserView(APIView):
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
                    "email": user.email,
                    "xray_uuid": str(user.xray_uuid),
                    "referral_code": user.referral_code,
                    "balance_kopeks": 0,
                    "has_used_trial": user.has_used_trial,
                    "is_legal_accepted": user.is_legal_accepted,
                    "legal_accepted_at": _iso_utc(user.legal_accepted_at),
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BotAcceptLegalView(APIView):
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
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TelegramAuthInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        accepted_legal = serializer.validated_data["accepted_legal"]
        ref_code = (serializer.validated_data.get("referred_by_code") or "").strip()
        auth_token = secrets.token_urlsafe(24)
        ttl = settings.TELEGRAM_AUTH_TTL_SECONDS
        link_to_user_id = request.user.id if request.user.is_authenticated else None

        cache.set(
            f"{TG_AUTH_CACHE_PREFIX}{auth_token}",
            {
                "status": "pending",
                "telegram_id": None,
                "user_id": None,
                "link_to_user_id": link_to_user_id,
                "accepted_legal": accepted_legal,
                "referred_by_code": ref_code,
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
        ref_code = str(data.get("referred_by_code") or "").strip()
        link_to_user_id = data.get("link_to_user_id")
        now = timezone.now()

        if link_to_user_id:
            web_user = User.objects.filter(id=link_to_user_id).first()
            tg_user = User.objects.filter(telegram_id=telegram_id).first()
            if web_user is not None:
                if tg_user is not None and tg_user.id != web_user.id:
                    if tg_user.email and web_user.email and tg_user.canonical_email != web_user.canonical_email:
                        return Response(
                            {"detail": "Этот Telegram уже привязан к другому email."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    user = merge_users(primary=web_user, secondary=tg_user)
                    user.telegram_username = telegram_username
                    user.save(update_fields=["telegram_username"])
                else:
                    web_user.telegram_id = telegram_id
                    web_user.telegram_username = telegram_username
                    if accepted_legal and not web_user.is_legal_accepted:
                        web_user.is_legal_accepted = True
                        web_user.legal_accepted_at = now
                    web_user.save()
                    user = web_user
            else:
                link_to_user_id = None

        if not link_to_user_id:
            referrer = None
            if ref_code:
                candidate = User.objects.filter(referral_code__iexact=ref_code).first()
                if candidate is not None and candidate.telegram_id != telegram_id:
                    referrer = candidate

            try:
                user, _ = User.objects.get_or_create(
                    telegram_id=telegram_id,
                    defaults={
                        "username": f"tg_{telegram_id}",
                        "telegram_username": telegram_username,
                        "referred_by": referrer,
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


class EmailOtpRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.RESEND_API_KEY and not settings.EMAIL_HOST and not settings.DEBUG:
            return Response(
                {"detail": "Отправка писем временно недоступна: почтовый шлюз не настроен."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = EmailOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cleaned_email, canonical = validate_email_domain(
                serializer.validated_data["email"],
                strict_for_trial=False,
            )
        except EmailValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        cd_key = f"{EMAIL_OTP_COOLDOWN_PREFIX}{canonical}"
        if cache.get(cd_key):
            return Response(
                {"detail": "Код уже отправлен. Повторная отправка доступна через минуту."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp_key = f"{EMAIL_OTP_PREFIX}{canonical}"
        cache.set(otp_key, {"code": code, "email": cleaned_email, "attempts": 0}, timeout=600)
        cache.set(cd_key, 1, timeout=60)

        try:
            send_mail(
                subject="Код входа в Linkori",
                message=(
                    f"Ваш код для входа в Linkori: {code}\n\n"
                    f"Код действует 10 минут. Никому не передавайте его."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[cleaned_email],
                fail_silently=False,
            )
        except Exception as exc:
            cache.delete(otp_key)
            cache.delete(cd_key)
            return Response(
                {"detail": f"Не удалось отправить письмо на почту: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"status": "sent", "email": cleaned_email, "expires_in": 600},
            status=status.HTTP_200_OK,
        )


class EmailOtpVerifyView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cleaned_email, canonical = validate_email_domain(
                serializer.validated_data["email"],
                strict_for_trial=False,
            )
        except EmailValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        entered_code = serializer.validated_data["code"].strip()
        otp_key = f"{EMAIL_OTP_PREFIX}{canonical}"
        record = cache.get(otp_key)
        if not isinstance(record, dict):
            return Response(
                {"detail": "Код истек или не запрашивался. Запросите новый код."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attempts = int(record.get("attempts", 0))
        if attempts >= 5:
            cache.delete(otp_key)
            return Response(
                {"detail": "Слишком много неверных попыток. Запросите новый код."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not secrets.compare_digest(entered_code, str(record.get("code", ""))):
            record["attempts"] = attempts + 1
            cache.set(otp_key, record, timeout=600)
            return Response({"detail": "Неверный код подтверждения."}, status=status.HTTP_400_BAD_REQUEST)

        cache.delete(otp_key)
        accepted_legal = serializer.validated_data["accepted_legal"]
        ref_code = (serializer.validated_data.get("referred_by_code") or "").strip()
        now = timezone.now()

        if request.user.is_authenticated:
            try:
                user = attach_or_merge_email(request.user, cleaned_email)
            except AccountLinkError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            user = User.objects.filter(canonical_email=canonical).first()
            if user is None:
                referrer = None
                if ref_code:
                    referrer = User.objects.filter(referral_code__iexact=ref_code).first()
                user = User.objects.create(
                    username=f"em_{secrets.token_hex(6)}",
                    email=cleaned_email,
                    canonical_email=canonical,
                    referred_by=referrer,
                    is_legal_accepted=accepted_legal,
                    legal_accepted_at=now if accepted_legal else None,
                )
            elif accepted_legal and not user.is_legal_accepted:
                user.is_legal_accepted = True
                user.legal_accepted_at = now
                user.save(update_fields=["is_legal_accepted", "legal_accepted_at"])

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        get_token(request)

        return Response(
            {"status": "confirmed", "user": _serialize_web_user(user)},
            status=status.HTTP_200_OK,
        )


class WebApplyReferralView(APIView):
    """
    Позволяет новому пользователю в кабинете ввести реферальный код
    в течение 24 часов после создания аккаунта (если код еще не применен).
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WebApplyReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if user.referred_by_id is not None:
            return Response(
                {"detail": "Реферальный код уже применен к вашему аккаунту."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if timezone.now() - user.date_joined > REFERRAL_WINDOW:
            return Response(
                {"detail": "Ввести реферальный код можно только в течение 24 часов после регистрации."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = serializer.validated_data["referral_code"].strip()
        referrer = User.objects.filter(referral_code__iexact=code).first()
        if referrer is None:
            return Response(
                {"detail": "Реферальный код не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if referrer.id == user.id:
            return Response(
                {"detail": "Нельзя указать собственный реферальный код."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if referrer.referred_by_id == user.id:
            return Response(
                {"detail": "Взаимная привязка рефералов запрещена."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.referred_by = referrer
        user.save(update_fields=["referred_by"])

        return Response(
            {"status": "ok", "message": "Реферальный код успешно применен!"},
            status=status.HTTP_200_OK,
        )


class WebMeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        get_token(request)
        user = request.user
        sub = get_active_subscription(user)
        referrals_count = User.objects.filter(referred_by=user).count()
        bonus_hours = (
            ReferralReward.objects.filter(referrer=user).aggregate(total=Sum("bonus_hours"))[
                "total"
            ]
            or 0
        )
        can_apply_referral = (
            user.referred_by_id is None
            and (timezone.now() - user.date_joined) <= REFERRAL_WINDOW
        )

        return Response(
            {
                "user": _serialize_web_user(user),
                "referrals_count": referrals_count,
                "referral_bonus_hours": bonus_hours,
                "has_referrer": user.referred_by_id is not None,
                "can_apply_referral": can_apply_referral,
                "active_subscription": serialize_subscription(sub) if sub else None,
                "devices_count": sub.devices.count() if sub else 0,
            },
            status=status.HTTP_200_OK,
        )


class WebLogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)