import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasBotToken(BasePermission):
    """
    Проверяет авторизующий токен Telegram-бота:
    Authorization: Bearer <BOT_API_TOKEN>
    или X-Bot-Token: <BOT_API_TOKEN>.
    """

    def has_permission(self, request, view) -> bool:
        expected = getattr(settings, "BOT_API_TOKEN", "")
        if not expected:
            return False

        token = request.headers.get("X-Bot-Token", "").strip()
        if not token:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()

        if not token:
            return False
        return secrets.compare_digest(token, expected)