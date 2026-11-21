import secrets

from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import BasePermission

from .models import ProbeStand


class HasProbeToken(BasePermission):
    """
    Проверяет токен стенда из заголовка Authorization: Bearer <token>
    или X-Probe-Token: <token>.
    Сначала ищет токен среди ProbeStand в БД, затем сверяет с общим PROBE_API_TOKEN.
    """

    def has_permission(self, request, view) -> bool:
        token = request.headers.get("X-Probe-Token", "").strip()
        if not token:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()

        if not token:
            return False

        stand = ProbeStand.objects.filter(token=token, is_active=True).first()
        if stand is not None:
            request.probe_stand = stand
            ProbeStand.objects.filter(pk=stand.pk).update(last_seen_at=timezone.now())
            return True

        expected = getattr(settings, "PROBE_API_TOKEN", "")
        if expected and secrets.compare_digest(token, expected):
            request.probe_stand = None
            return True

        return False