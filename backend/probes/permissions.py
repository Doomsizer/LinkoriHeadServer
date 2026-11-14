import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasProbeToken(BasePermission):
    """
    Проверяет токен стенда из заголовка:
    Authorization: Bearer <PROBE_API_TOKEN>
    или X-Probe-Token: <PROBE_API_TOKEN>.
    """

    def has_permission(self, request, view) -> bool:
        expected = getattr(settings, "PROBE_API_TOKEN", "")
        if not expected:
            return False

        token = request.headers.get("X-Probe-Token", "").strip()
        if not token:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()

        if not token:
            return False
        return secrets.compare_digest(token, expected)