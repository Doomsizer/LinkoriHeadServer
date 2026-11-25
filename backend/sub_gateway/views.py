import base64
import re
from collections import Counter
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from billing.models import Subscription, SubscriptionDevice
from nodes.models import NodeInbound
from probes.country_utils import (
    detect_country_code,
    extract_origin_bucket,
    get_country_rank,
)
from probes.models import WorkingPublicConfig

from .uri_builder import build_happ_json_payload, build_subscription_payload

HWID_REGEX = re.compile(r"^[a-zA-Z0-9=_-]{8,128}$")

MAX_ITEMS_PER_NETWORK_SUB = 30
MAX_ITEMS_GENERAL_SUB = 40
TAIL_EXTRA_COUNTRIES_COUNT = 5

DEEPLINK_SCHEMES = {
    "happ": ("Happ", "happ://add/{sub_url}"),
    "v2raytun": ("v2RayTun", "v2raytun://import/{sub_url}"),
    "hiddify": ("Hiddify", "hiddify://import/{sub_url}"),
    "incy": ("INCY", "incy://import/{sub_url}"),
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


def is_happ_json_client(request, user_agent: str) -> bool:
    fmt = request.GET.get("format", "").lower().strip()
    if fmt == "uri":
        return False
    if fmt in ("xray", "json"):
        return True
    return "happ" in user_agent.lower()


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

    headers = {
        "profile-title": f"base64:{title_b64}",
        "profile-update-interval": str(settings.SUB_UPDATE_INTERVAL_HOURS),
        "subscription-userinfo": userinfo,
        "content-disposition": 'attachment; filename="linkori"',
        "support-url": settings.SUB_SUPPORT_URL,
        "profile-web-page-url": settings.SUB_WEB_URL,
        "x-hwid-active": "true",
    }

    announce_text = getattr(settings, "SUB_ANNOUNCE_TEXT", "").strip()
    if announce_text:
        announce_b64 = base64.b64encode(announce_text.encode("utf-8")).decode("ascii")
        headers["announce"] = f"base64:{announce_b64}"
    announce_url = getattr(settings, "SUB_ANNOUNCE_URL", "").strip()
    if announce_url:
        headers["announce-url"] = announce_url

    return headers


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
    # Все наши включенные инбаунды всегда попадают в подписку (при падении шлем алерт админу)
    inbounds = list(
        NodeInbound.objects.select_related("node").filter(
            is_enabled=True,
            node__is_enabled=True,
        )
    )

    def inbound_sort_key(inb: NodeInbound):
        tier, c_prio, c_code = get_country_rank(inb.node.country_code)
        lat = (
            inb.lte_latency_ms
            if network_type == "lte"
            else (inb.wifi_latency_ms if network_type == "wifi" else inb.last_latency_ms)
        )
        return (
            tier,
            c_prio,
            c_code,
            inb.node.priority,
            lat if lat is not None else 10**9,
            inb.id,
        )

    inbounds.sort(key=inbound_sort_key)
    return inbounds


def _pick_diverse(
    items: list[dict],
    limit: int,
    prefer_distinct_tiers: bool = False,
) -> tuple[list[dict], list[dict]]:
    if limit <= 0 or not items:
        return [], list(items)

    remaining = list(items)
    chosen_list: list[dict] = []
    origin_counts: Counter[str] = Counter()
    proto_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()
    tier_counts: Counter[int] = Counter()

    while remaining and len(chosen_list) < limit:
        best_idx = 0
        best_score = None
        for idx, item in enumerate(remaining):
            is_unknown_country = 1 if item["country_code"] == "ZZ" else 0
            if prefer_distinct_tiers:
                score = (
                    is_unknown_country,
                    country_counts[item["country_code"]],
                    tier_counts[item["tier"]],
                    origin_counts[item["origin"]],
                    proto_counts[item["proto"]],
                    item["latency"],
                    item["id"],
                )
            else:
                score = (
                    is_unknown_country,
                    country_counts[item["country_code"]],
                    origin_counts[item["origin"]],
                    proto_counts[item["proto"]],
                    item["country_prio"],
                    item["latency"],
                    item["id"],
                )
            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

        chosen = remaining.pop(best_idx)
        chosen_list.append(chosen)
        origin_counts[chosen["origin"]] += 1
        proto_counts[chosen["proto"]] += 1
        country_counts[chosen["country_code"]] += 1
        tier_counts[chosen["tier"]] += 1

    return chosen_list, remaining


def _select_working_public_uris(network_type: str | None, quota: int) -> list[str]:
    if quota <= 0:
        return []

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

    candidates_by_hash: dict[str, dict] = {}
    for cfg in qs:
        parsed = urlparse(cfg.uri)
        if parsed.hostname and parsed.port:
            ep = (_uri_protocol_family(cfg.uri), parsed.hostname.lower(), int(parsed.port))
            if ep in own_endpoint_keys:
                continue

        cc = (cfg.country_code or "").upper().strip() or detect_country_code(cfg.uri)
        tier, c_prio, c_code = get_country_rank(cc)
        proto_fam = _uri_protocol_family(cfg.uri)
        origin_key = extract_origin_bucket(cfg.origin_source, cfg.uri)
        lat = cfg.latency_ms if cfg.latency_ms is not None else 10**9

        prev = candidates_by_hash.get(cfg.uri_hash)
        if prev is None or (origin_key != "unknown" and prev["origin"] == "unknown") or lat < prev["latency"]:
            candidates_by_hash[cfg.uri_hash] = {
                "id": cfg.id,
                "uri": cfg.uri,
                "tier": tier,
                "country_prio": c_prio,
                "country_code": c_code,
                "proto": proto_fam,
                "origin": origin_key,
                "latency": lat,
            }

    pool = list(candidates_by_hash.values())
    if not pool:
        return []

    core_pool = [item for item in pool if item["tier"] == 0]
    extra_pool = [item for item in pool if item["tier"] > 0]

    desired_extra = min(
        TAIL_EXTRA_COUNTRIES_COUNT if quota >= 15 else max(1, quota // 3),
        len(extra_pool),
    )
    extra_selected, extra_leftover = _pick_diverse(
        extra_pool,
        limit=desired_extra,
        prefer_distinct_tiers=True,
    )

    core_quota = max(0, quota - len(extra_selected))
    core_selected, _ = _pick_diverse(
        core_pool,
        limit=core_quota,
        prefer_distinct_tiers=False,
    )

    remaining_slots = quota - len(core_selected) - len(extra_selected)
    if remaining_slots > 0 and extra_leftover:
        extra_topup, _ = _pick_diverse(
            extra_leftover,
            limit=remaining_slots,
            prefer_distinct_tiers=True,
        )
        extra_selected.extend(extra_topup)

    core_selected.sort(
        key=lambda x: (x["country_prio"], x["country_code"], x["proto"], x["latency"], x["id"])
    )
    extra_selected.sort(
        key=lambda x: (
            x["tier"],
            x["country_prio"],
            x["country_code"],
            x["proto"],
            x["latency"],
            x["id"],
        )
    )

    return [item["uri"] for item in core_selected] + [item["uri"] for item in extra_selected]


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
            prefix = f"{base_sub_url}/{net}" if net else base_sub_url
            context = {
                "sub_exists": subscription is not None,
                "web_url": settings.SUB_WEB_URL,
                "support_url": settings.SUB_SUPPORT_URL,
                "plan_name": subscription.plan.name if subscription else "",
                "expires_date": (
                    subscription.expires_at.strftime("%d.%m.%Y") if subscription else ""
                ),
                "sub_url": prefix,
                "sub_lte_url": f"{base_sub_url}/lte",
                "sub_wifi_url": f"{base_sub_url}/wifi",
                "open_happ_url": f"{prefix}/open/happ",
                "open_v2raytun_url": f"{prefix}/open/v2raytun",
                "open_hiddify_url": f"{prefix}/open/hiddify",
                "open_incy_url": f"{prefix}/open/incy",
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

        # 6. Лимит: 30 для LTE/Wi-Fi и 40 для общей подписки
        max_items = MAX_ITEMS_PER_NETWORK_SUB if net in ("lte", "wifi") else MAX_ITEMS_GENERAL_SUB
        max_real_servers = max_items - 1

        inbounds = _select_live_inbounds(network_type=net)[:max_real_servers]
        public_quota = max(0, max_real_servers - len(inbounds))
        public_uris = _select_working_public_uris(network_type=net, quota=public_quota)

        # 7. Для Happ — Xray JSON с burstObservatory (автопереключение), остальным — base64
        if is_happ_json_client(request, user_agent):
            payload = build_happ_json_payload(
                subscription=subscription,
                inbounds=inbounds,
                network_type=net,
                extra_uris=public_uris,
            )
            content_type = "application/json; charset=utf-8"
        else:
            payload = build_subscription_payload(
                subscription=subscription,
                inbounds=inbounds,
                device_os=device_os,
                user_agent=user_agent,
                network_type=net,
                extra_uris=public_uris,
            )
            content_type = "text/plain; charset=utf-8"

        response = HttpResponse(payload, content_type=content_type, status=200)
        for header_name, header_value in build_subscription_headers(
            subscription, network_type=net
        ).items():
            response[header_name] = header_value
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response