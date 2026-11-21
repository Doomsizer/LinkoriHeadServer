import base64
import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from billing.models import Subscription, SubscriptionDevice
from nodes.models import NodeInbound
from probes.models import WorkingPublicConfig

from .uri_builder import build_subscription_payload

HWID_REGEX = re.compile(r"^[a-zA-Z0-9=_-]{8,128}$")

DEEPLINK_SCHEMES = {
    "happ": ("Happ", "happ://add/{sub_url}"),
    "v2raytun": ("v2RayTun", "v2raytun://import/{sub_url}"),
    "hiddify": ("Hiddify", "hiddify://import/{sub_url}"),
}


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


def build_subscription_headers(
    subscription: Subscription,
    network_type: str | None = None,
) -> dict[str, str]:
    title = settings.SUB_PROFILE_TITLE
    if network_type == "lte":
        title = f"{title} LTE"
    elif network_type == "wifi":
        title = f"{title} Wi-Fi"

    title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
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
        "x-hwid-active": "true",
    }


def _uri_protocol_family(uri: str) -> str:
    scheme = uri.split("://", 1)[0].lower().strip()
    if scheme in ("hy2", "hysteria2"):
        return "hysteria2"
    return scheme


def _inbound_protocol_family(inbound: NodeInbound) -> str:
    if inbound.protocol == NodeInbound.Protocol.HYSTERIA2:
        return "hysteria2"
    if inbound.protocol in (
        NodeInbound.Protocol.VLESS_REALITY,
        NodeInbound.Protocol.VLESS_WS,
    ):
        return "vless"
    return inbound.protocol


def _select_live_inbounds(network_type: str | None) -> list[NodeInbound]:
    base_qs = NodeInbound.objects.select_related("node").filter(
        is_enabled=True,
        node__is_enabled=True,
    )
    live_statuses = [NodeInbound.HealthStatus.ONLINE, NodeInbound.HealthStatus.DEGRADED]

    if network_type == "lte":
        return list(
            base_qs.filter(lte_health_status__in=live_statuses).order_by("node__priority", "id")
        )
    if network_type == "wifi":
        return list(
            base_qs.filter(wifi_health_status__in=live_statuses).order_by("node__priority", "id")
        )
    return list(base_qs.filter(health_status__in=live_statuses).order_by("node__priority", "id"))


def _select_working_public_uris(network_type: str | None) -> list[str]:
    own_endpoint_keys: set[tuple[str, str, int]] = set()
    for inb in NodeInbound.objects.select_related("node").filter(
        is_enabled=True,
        node__is_enabled=True,
    ):
        fam = _inbound_protocol_family(inb)
        own_endpoint_keys.add((fam, inb.connect_host.lower(), int(inb.connect_port)))
        own_endpoint_keys.add((fam, str(inb.node.ip_address).lower(), int(inb.connect_port)))

    qs = WorkingPublicConfig.objects.filter(is_active=True).order_by("id")
    if network_type == "lte":
        qs = qs.filter(source="lte")
    elif network_type == "wifi":
        qs = qs.filter(source="wifi")

    seen_hashes: set[str] = set()
    uris: list[str] = []
    for cfg in qs:
        if cfg.uri_hash in seen_hashes:
            continue
        parsed = urlparse(cfg.uri)
        if parsed.hostname and parsed.port:
            ep = (_uri_protocol_family(cfg.uri), parsed.hostname.lower(), int(parsed.port))
            if ep in own_endpoint_keys:
                continue
        seen_hashes.add(cfg.uri_hash)
        uris.append(cfg.uri)
    return uris


class SubscriptionOpenAppView(View):
    http_method_names = ["get", "head"]
    network_type: str | None = None

    def get(self, request, sub_token: str, app_name: str):
        app_entry = DEEPLINK_SCHEMES.get(app_name.lower())
        if app_entry is None:
            return HttpResponse(status=404)

        if not Subscription.objects.filter(sub_token=sub_token).exists():
            return HttpResponse(status=404)

        app_label, template_uri = app_entry
        net = self.network_type or request.GET.get("net", "").lower().strip()
        if net in ("lte", "wifi"):
            sub_url = f"https://{settings.SUB_GATEWAY_HOST}/{sub_token}/{net}"
        else:
            sub_url = f"https://{settings.SUB_GATEWAY_HOST}/{sub_token}"

        deeplink = template_uri.format(sub_url=sub_url)
        response = render(
            request,
            "sub_gateway/open_app.html",
            {
                "app_label": app_label,
                "deeplink": deeplink,
                "sub_url": sub_url,
            },
            status=200,
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class SubscriptionGatewayView(View):
    http_method_names = ["get", "head"]
    network_type: str | None = None

    def get(self, request, sub_token: str):
        net = self.network_type or request.GET.get("net", "").lower().strip()
        if net not in ("lte", "wifi"):
            net = None

        subscription = (
            Subscription.objects.select_related("user", "plan")
            .filter(sub_token=sub_token)
            .first()
        )

        # 1. Отсекаем браузеры красивой страницей без конфигов серверов
        if is_browser_request(request):
            base_sub_url = f"https://{settings.SUB_GATEWAY_HOST}/{sub_token}"
            context = {
                "sub_exists": subscription is not None,
                "web_url": settings.SUB_WEB_URL,
                "support_url": settings.SUB_SUPPORT_URL,
                "plan_name": subscription.plan.name if subscription else "",
                "expires_date": (
                    subscription.expires_at.strftime("%d.%m.%Y") if subscription else ""
                ),
                "sub_url": f"{base_sub_url}/{net}" if net else base_sub_url,
                "sub_lte_url": f"{base_sub_url}/lte",
                "sub_wifi_url": f"{base_sub_url}/wifi",
                "open_happ_url": (
                    f"{base_sub_url}/{net}/open/happ" if net else f"{base_sub_url}/open/happ"
                ),
                "open_v2raytun_url": (
                    f"{base_sub_url}/{net}/open/v2raytun"
                    if net
                    else f"{base_sub_url}/open/v2raytun"
                ),
                "open_hiddify_url": (
                    f"{base_sub_url}/{net}/open/hiddify"
                    if net
                    else f"{base_sub_url}/open/hiddify"
                ),
            }
            response = render(
                request,
                "sub_gateway/browser_stub.html",
                context,
                status=200,
            )
            response["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response

        # 2. Токен не найден
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
            for k, v in build_subscription_headers(subscription, network_type=net).items():
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

        # 6. Собираем наши живые инбаунды + рабочие внешние конфиги стенда
        inbounds = _select_live_inbounds(network_type=net)
        public_uris = _select_working_public_uris(network_type=net)

        # 7. Собираем base64-подписку с «⚡ Лучший сервер» в начале
        payload = build_subscription_payload(
            subscription=subscription,
            inbounds=inbounds,
            device_os=device_os,
            user_agent=user_agent,
            network_type=net,
            extra_uris=public_uris,
        )

        response = HttpResponse(
            payload,
            content_type="text/plain; charset=utf-8",
            status=200,
        )
        for header_name, header_value in build_subscription_headers(
            subscription, network_type=net
        ).items():
            response[header_name] = header_value
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response