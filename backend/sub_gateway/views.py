import base64
import re

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from billing.models import Subscription, SubscriptionDevice
from nodes.models import NodeInbound

from .uri_builder import build_subscription_payload

HWID_REGEX = re.compile(r"^[a-zA-Z0-9=_-]{8,128}$")


def get_client_ip(request) -> str | None:
    x_real_ip = request.headers.get("X-Real-IP", "").strip()
    if x_real_ip:
        return x_real_ip
    x_forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if x_forwarded_for:
        return x_forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")


def is_browser_request(request) -> bool:
    if request.headers.get("x-hwid"):
        return False
    sec_fetch_dest = request.headers.get("Sec-Fetch-Dest", "").lower()
    accept = request.headers.get("Accept", "").lower()
    if sec_fetch_dest == "document":
        return True
    if "text/html" in accept and "application/xhtml+xml" in accept:
        return True
    if accept.startswith("text/html"):
        return True
    return False


def build_subscription_headers(subscription: Subscription) -> dict[str, str]:
    title_b64 = base64.b64encode(settings.SUB_PROFILE_TITLE.encode("utf-8")).decode("ascii")
    expire_ts = int(subscription.expires_at.timestamp())
    userinfo = (
        f"upload=0; download={subscription.traffic_used_bytes}; "
        f"total={subscription.traffic_limit_bytes}; expire={expire_ts}"
    )
    return {
        "profile-title": f"base64:{title_b64}",
        "profile-update-interval": str(settings.SUB_UPDATE_INTERVAL_HOURS),
        "subscription-userinfo": userinfo,
        "content-disposition": 'attachment; filename="linkori"',
        "support-url": settings.SUB_SUPPORT_URL,
        "profile-web-page-url": settings.SUB_WEB_URL,
        "x-hwid-active": "true",}


class SubscriptionGatewayView(View):
    http_method_names = ["get", "head"]

    def get(self, request, sub_token: str):
        # 1. Отсекаем браузеры HTML-заглушкой без конфигов
        if is_browser_request(request):
            response = render(
                request,
                "sub_gateway/browser_stub.html",
                {"web_url": settings.SUB_WEB_URL},
                status=200,
            )
            response["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response

        # 2. Ищем подписку по токену
        subscription = (
            Subscription.objects.select_related("user", "plan")
            .filter(sub_token=sub_token)
            .first()
        )
        if subscription is None:
            return HttpResponse(status=404)

        # 3. Проверяем наличие и корректность x-hwid
        raw_hwid = request.headers.get("x-hwid", "").strip()
        if not raw_hwid or not HWID_REGEX.match(raw_hwid):
            response = HttpResponse(status=403)
            response["x-hwid-active"] = "true"
            response["x-hwid-not-supported"] = "true"
            response["Cache-Control"] = "no-store"
            return response

        # 4. Проверяем активность подписки, срок действия и лимит трафика
        if not subscription.is_valid_now(timezone.now()):
            response = HttpResponse(status=403)
            for k, v in build_subscription_headers(subscription).items():
                response[k] = v
            response["Cache-Control"] = "no-store"
            return response

        device_os = request.headers.get("x-device-os", "").strip()[:64]
        ver_os = request.headers.get("x-ver-os", "").strip()[:64]
        device_model = request.headers.get("x-device-model", "").strip()[:128]
        user_agent = request.headers.get("User-Agent", "").strip()[:255]
        client_ip = get_client_ip(request)

        # 5. Атомарная проверка лимита устройств и регистрация HWID
        with transaction.atomic():
            locked_sub = Subscription.objects.select_for_update().get(pk=subscription.pk)
            device = SubscriptionDevice.objects.filter(
                subscription=locked_sub,
                hwid=raw_hwid,
            ).first()

            if device is not None:
                if device.is_blocked:
                    response = HttpResponse(status=403)
                    response["x-hwid-active"] = "true"
                    response["Cache-Control"] = "no-store"
                    return response

                if device_os:
                    device.device_os = device_os
                if ver_os:
                    device.ver_os = ver_os
                if device_model:
                    device.device_model = device_model
                if user_agent:
                    device.user_agent = user_agent
                if client_ip:
                    device.last_ip = client_ip
                device.save(
                    update_fields=[
                        "device_os",
                        "ver_os",
                        "device_model",
                        "user_agent",
                        "last_ip",
                        "last_seen_at",
                    ]
                )
            else:
                current_devices = SubscriptionDevice.objects.filter(
                    subscription=locked_sub
                ).count()
                if current_devices >= locked_sub.max_devices:
                    response = HttpResponse(status=403)
                    response["x-hwid-active"] = "true"
                    response["x-hwid-max-devices-reached"] = "true"
                    response["x-hwid-limit"] = "true"
                    response["Cache-Control"] = "no-store"
                    return response

                SubscriptionDevice.objects.create(
                    subscription=locked_sub,
                    hwid=raw_hwid,
                    device_os=device_os,
                    ver_os=ver_os,
                    device_model=device_model,
                    user_agent=user_agent,
                    last_ip=client_ip,
                )

        # 6. Выбираем только включенные и живые инбаунды (online / degraded)
        inbounds = (
            NodeInbound.objects.select_related("node")
            .filter(
                is_enabled=True,
                node__is_enabled=True,
                health_status__in=[
                    NodeInbound.HealthStatus.ONLINE,
                    NodeInbound.HealthStatus.DEGRADED,
                ],
            )
            .order_by("node__priority", "id")
        )

        # 7. Собираем base64-подписку с учетом клиента (SIP022 / SIP002 для iOS)
        payload = build_subscription_payload(
            subscription=subscription,
            inbounds=inbounds,
            device_os=device_os,
            user_agent=user_agent,
        )

        response = HttpResponse(
            payload,
            content_type="text/plain; charset=utf-8",
            status=200,
        )
        for header_name, header_value in build_subscription_headers(subscription).items():
            response[header_name] = header_value
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    }
