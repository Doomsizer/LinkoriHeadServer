import base64
import json
from collections.abc import Iterable
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from billing.models import Subscription
from nodes.models import NodeInbound
from probes.country_utils import get_country_display, get_country_rank

MAX_AUTO_OUTBOUNDS = 18

# Потолок outbound'ов в одном Xray JSON конфиге. Happ на iOS держит ядро в
# 50 МБ, поэтому большие списки в один конфиг не складываем.
MAX_OUTBOUNDS_PER_CONFIG = 18

# Потолок числа профилей в JSON подписке. Happ запускает отдельное ядро на каждый
# профиль, поэтому 40+ конфигов дают минутную проверку и жрут память на iOS.
MAX_XRAY_CONFIGS = 16

# Проба идет через сам прокси (хендшейк + TLS до пробного хоста), поэтому на LTE
# и до дальних нод ей нужен запас по времени. Цикл проверки = interval * sampling.
BURST_PING_INTERVAL = "15s"
BURST_PING_SAMPLING = 3
BURST_PING_TIMEOUT = "5s"
LEAST_LOAD_MAX_RTT = "2500ms"
# Доля допустимых провалов в выборке: 1 провал из 3 проб проходит, 2 из 3 отсекаются.
LEAST_LOAD_TOLERANCE = 0.5


def _format_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _build_label(inbound: NodeInbound, remark_override: str | None = None) -> str:
    if remark_override:
        return remark_override.strip()
    flag = inbound.node.flag_emoji.strip()
    name = inbound.display_name.strip()
    if flag and not name.startswith(flag):
        return f"{flag} {name}"
    return name


def _build_remark(inbound: NodeInbound, remark_override: str | None = None) -> str:
    return quote(_build_label(inbound, remark_override=remark_override), safe="")


def _replace_uri_remark(uri: str, new_remark: str) -> str:
    base = uri.split("#", 1)[0]
    return f"{base}#{quote(new_remark, safe='')}"


def _clean_query(params: dict[str, str | int | None]) -> str:
    filtered = {k: str(v) for k, v in params.items() if v is not None and v != ""}
    return urlencode(filtered)


def _normalize_pin_sha256(pin: str) -> str:
    cleaned = pin.strip()
    if not cleaned:
        return ""
    no_colons = cleaned.replace(":", "")
    if len(no_colons) == 64 and all(c in "0123456789abcdefABCDEF" for c in no_colons):
        return no_colons.lower()
    return cleaned


def build_vless_reality_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    remark_override: str | None = None,
) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    net_type = str(extra.get("type", "tcp") or "tcp").lower()
    flow = "" if net_type == "grpc" else str(extra.get("flow", "xtls-rprx-vision") or "")

    query_params: dict[str, str | int | None] = {
        "type": net_type,
        "security": "reality",
        "pbk": extra.get("pbk", ""),
        "fp": extra.get("fp", "chrome"),
        "sni": extra.get("sni", ""),
        "sid": extra.get("sid", ""),
        "spx": extra.get("spx", "/"),
        "flow": flow,
    }
    if net_type == "grpc":
        query_params["serviceName"] = extra.get("service_name", "")
        if extra.get("multi_mode"):
            query_params["mode"] = "multi"
        if extra.get("authority"):
            query_params["authority"] = extra.get("authority")

    query = _clean_query(query_params)
    remark = _build_remark(inbound, remark_override=remark_override)
    return f"vless://{subscription.xray_uuid}@{host}:{inbound.connect_port}?{query}#{remark}"


def build_vless_ws_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    remark_override: str | None = None,
) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    ws_host = extra.get("host") or extra.get("sni") or inbound.connect_host
    query = _clean_query(
        {
            "type": "ws",
            "security": extra.get("security", "tls"),
            "path": extra.get("path", "/"),
            "host": ws_host,
            "sni": extra.get("sni", ws_host),
            "fp": extra.get("fp", "chrome"),
            "alpn": extra.get("alpn", "http/1.1"),
        }
    )
    remark = _build_remark(inbound, remark_override=remark_override)
    return f"vless://{subscription.xray_uuid}@{host}:{inbound.connect_port}?{query}#{remark}"


def build_hysteria2_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    remark_override: str | None = None,
) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    auth = quote(str(subscription.xray_uuid), safe="")

    insecure = extra.get("insecure")
    if isinstance(insecure, bool):
        insecure = "1" if insecure else "0"

    query = _clean_query(
        {
            "sni": extra.get("sni", ""),
            "alpn": extra.get("alpn", ""),
            "insecure": insecure,
            "obfs": extra.get("obfs", ""),
            "obfs-password": extra.get("obfs_password", ""),
            "pinSHA256": extra.get("pin_sha256", ""),
            "mport": extra.get("mport", ""),
        }
    )
    remark = _build_remark(inbound, remark_override=remark_override)
    qs = f"?{query}" if query else ""
    return f"hysteria2://{auth}@{host}:{inbound.connect_port}/{qs}#{remark}"


def build_inbound_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    device_os: str = "",
    user_agent: str = "",
    remark_override: str | None = None,
) -> str:
    protocol = inbound.protocol
    if protocol == NodeInbound.Protocol.VLESS_REALITY:
        return build_vless_reality_uri(subscription, inbound, remark_override=remark_override)
    if protocol == NodeInbound.Protocol.VLESS_WS:
        return build_vless_ws_uri(subscription, inbound, remark_override=remark_override)
    if protocol == NodeInbound.Protocol.HYSTERIA2:
        return build_hysteria2_uri(subscription, inbound, remark_override=remark_override)
    raise ValueError(f"Неподдерживаемый протокол инбаунда: {protocol}")


def _get_inbound_latency(inbound: NodeInbound, network_type: str | None) -> int | None:
    if network_type == "lte":
        return inbound.lte_latency_ms if inbound.lte_latency_ms is not None else inbound.last_latency_ms
    if network_type == "wifi":
        return inbound.wifi_latency_ms if inbound.wifi_latency_ms is not None else inbound.last_latency_ms
    return inbound.last_latency_ms


def _get_inbound_health_rank(inbound: NodeInbound, network_type: str | None) -> int:
    status = (
        inbound.lte_health_status
        if network_type == "lte"
        else (inbound.wifi_health_status if network_type == "wifi" else inbound.health_status)
    )
    if status == NodeInbound.HealthStatus.ONLINE:
        return 0
    if status == NodeInbound.HealthStatus.DEGRADED:
        return 1
    if status == NodeInbound.HealthStatus.UNKNOWN:
        return 2
    return 3


def select_best_inbound(
    inbounds: list[NodeInbound],
    network_type: str | None = None,
) -> tuple[NodeInbound | None, int | None]:
    if not inbounds:
        return None, None

    def sort_key(inb: NodeInbound):
        h_rank = _get_inbound_health_rank(inb, network_type)
        lat = _get_inbound_latency(inb, network_type)
        return (h_rank, lat is None, lat if lat is not None else 10**9, inb.node.priority, inb.id)

    best = min(inbounds, key=sort_key)
    return best, _get_inbound_latency(best, network_type)


def _inbound_preference_key(inbound: NodeInbound, network_type: str | None) -> tuple:
    latency = _get_inbound_latency(inbound, network_type)
    return (
        _get_inbound_health_rank(inbound, network_type),
        latency is None,
        latency if latency is not None else 10**9,
        inbound.node.priority,
        inbound.id,
    )


def build_subscription_payload(
    subscription: Subscription,
    inbounds: Iterable[NodeInbound],
    device_os: str = "",
    user_agent: str = "",
    network_type: str | None = None,
    extra_uris: Iterable[str] = (),
) -> str:
    inbound_list = list(inbounds)
    public_uris = [u.strip() for u in extra_uris if u and u.strip()]
    uris: list[str] = []

    best_inbound, _ = select_best_inbound(inbound_list, network_type=network_type)
    if best_inbound is not None:
        uris.append(
            build_inbound_uri(
                subscription=subscription,
                inbound=best_inbound,
                device_os=device_os,
                user_agent=user_agent,
                remark_override="⭐ Автовыбор",
            )
        )
    elif public_uris:
        uris.append(_replace_uri_remark(public_uris[0], "⭐ Автовыбор"))

    for inbound in inbound_list:
        uris.append(
            build_inbound_uri(
                subscription=subscription,
                inbound=inbound,
                device_os=device_os,
                user_agent=user_agent,
            )
        )

    uris.extend(public_uris)

    raw_text = "\n".join(uris)
    return base64.b64encode(raw_text.encode("utf-8")).decode("ascii")


def _inbound_to_xray_outbound(
    subscription: Subscription,
    inbound: NodeInbound,
    tag: str,
) -> dict | None:
    extra = inbound.extra_params or {}
    host = inbound.connect_host
    port = int(inbound.connect_port)

    if inbound.protocol == NodeInbound.Protocol.VLESS_REALITY:
        net_type = str(extra.get("type", "tcp") or "tcp").lower()
        flow = "" if net_type == "grpc" else str(extra.get("flow", "xtls-rprx-vision") or "").strip()
        user_obj = {"id": str(subscription.xray_uuid), "encryption": "none"}
        if flow:
            user_obj["flow"] = flow

        stream: dict = {
            "network": net_type,
            "security": "reality",
            "realitySettings": {
                "publicKey": str(extra.get("pbk", "")),
                "fingerprint": str(extra.get("fp", "chrome") or "chrome"),
                "serverName": str(extra.get("sni", "")),
                "shortId": str(extra.get("sid", "")),
                "spiderX": str(extra.get("spx", "/") or "/"),
            },
        }
        if net_type == "grpc":
            grpc_settings: dict = {"serviceName": str(extra.get("service_name", "") or "")}
            if extra.get("multi_mode"):
                grpc_settings["multiMode"] = True
            if extra.get("authority"):
                grpc_settings["authority"] = str(extra.get("authority"))
            stream["grpcSettings"] = grpc_settings

        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {"vnext": [{"address": host, "port": port, "users": [user_obj]}]},
            "streamSettings": stream,
        }

    if inbound.protocol == NodeInbound.Protocol.VLESS_WS:
        ws_host = str(extra.get("host") or extra.get("sni") or host)
        sni = str(extra.get("sni") or ws_host)
        security = str(extra.get("security", "tls") or "tls")
        alpn_str = str(extra.get("alpn", "http/1.1") or "http/1.1")
        alpn_list = [x.strip() for x in alpn_str.split(",") if x.strip()]

        stream = {
            "network": "ws",
            "security": security,
            "wsSettings": {
                "path": str(extra.get("path", "/") or "/"),
                "host": ws_host,
            },
        }
        if security == "tls":
            stream["tlsSettings"] = {
                "serverName": sni,
                "fingerprint": str(extra.get("fp", "chrome") or "chrome"),
                "alpn": alpn_list or ["http/1.1"],
            }
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": host,
                        "port": port,
                        "users": [{"id": str(subscription.xray_uuid), "encryption": "none"}],
                    }
                ]
            },
            "streamSettings": stream,
        }

    if inbound.protocol == NodeInbound.Protocol.HYSTERIA2:
        alpn_str = str(extra.get("alpn", "h3") or "h3")
        alpn_list = [x.strip() for x in alpn_str.split(",") if x.strip()] or ["h3"]
        tls_settings: dict = {
            "alpn": alpn_list,
            "allowInsecure": bool(extra.get("insecure")),
        }
        sni = str(extra.get("sni", "") or "").strip()
        if sni:
            tls_settings["serverName"] = sni
        pin_hex = _normalize_pin_sha256(str(extra.get("pin_sha256", "") or ""))
        if pin_hex:
            tls_settings["pinnedPeerCertSha256"] = pin_hex

        stream = {
            "network": "hysteria",
            "security": "tls",
            "tlsSettings": tls_settings,
            "hysteriaSettings": {
                "version": 2,
                "auth": str(subscription.xray_uuid),
            },
        }
        obfs = str(extra.get("obfs", "") or "").strip()
        obfs_pwd = str(extra.get("obfs_password", "") or "").strip()
        if obfs == "salamander" and obfs_pwd:
            stream["finalmask"] = {
                "udp": [{"type": "salamander", "settings": {"password": obfs_pwd}}]
            }

        return {
            "tag": tag,
            "protocol": "hysteria",
            "settings": {"version": 2, "address": host, "port": port},
            "streamSettings": stream,
        }

    return None


def _uri_to_xray_outbound(uri: str, tag: str) -> dict | None:
    parsed = urlparse(uri.strip())
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None

    params = parse_qs(parsed.query, keep_blank_values=True)

    def q(name: str, default: str = "") -> str:
        vals = params.get(name)
        return unquote(vals[0]) if vals else default

    if scheme == "vless":
        uuid_str = unquote(parsed.username or "")
        if not uuid_str:
            return None
        net_type = q("type", "tcp").lower() or "tcp"
        security = q("security", "none").lower() or "none"
        flow = "" if net_type == "grpc" else q("flow", "").strip()
        encryption = q("encryption", "none") or "none"

        user_obj = {"id": uuid_str, "encryption": encryption}
        if flow:
            user_obj["flow"] = flow

        stream: dict = {"network": net_type, "security": security}
        if security == "reality":
            stream["realitySettings"] = {
                "publicKey": q("pbk"),
                "fingerprint": q("fp", "chrome") or "chrome",
                "serverName": q("sni"),
                "shortId": q("sid"),
                "spiderX": q("spx", "/") or "/",
            }
        elif security == "tls":
            alpn_raw = q("alpn")
            tls_settings: dict = {
                "allowInsecure": q("allowInsecure") in ("1", "true") or q("insecure") in ("1", "true"),
            }
            if q("sni"):
                tls_settings["serverName"] = q("sni")
            if q("fp"):
                tls_settings["fingerprint"] = q("fp")
            if alpn_raw:
                tls_settings["alpn"] = [x.strip() for x in alpn_raw.split(",") if x.strip()]
            stream["tlsSettings"] = tls_settings

        if net_type == "ws":
            ws_settings: dict = {"path": q("path", "/") or "/"}
            ws_host = q("host") or q("sni")
            if ws_host:
                ws_settings["host"] = ws_host
            stream["wsSettings"] = ws_settings
        elif net_type == "grpc":
            grpc_settings: dict = {}
            if q("serviceName"):
                grpc_settings["serviceName"] = q("serviceName")
            if q("mode"):
                grpc_settings["multiMode"] = q("mode") == "multi"
            if q("authority"):
                grpc_settings["authority"] = q("authority")
            stream["grpcSettings"] = grpc_settings

        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {"vnext": [{"address": host, "port": int(port), "users": [user_obj]}]},
            "streamSettings": stream,
        }

    if scheme in ("hy2", "hysteria2"):
        user_part = unquote(parsed.username or "")
        pass_part = unquote(parsed.password or "")
        auth = f"{user_part}:{pass_part}" if pass_part else user_part
        if not auth:
            return None

        alpn_raw = q("alpn", "h3")
        alpn_list = [x.strip() for x in alpn_raw.split(",") if x.strip()] or ["h3"]
        tls_settings = {
            "alpn": alpn_list,
            "allowInsecure": q("insecure") in ("1", "true", "yes"),
        }
        if q("sni"):
            tls_settings["serverName"] = q("sni")
        pin_hex = _normalize_pin_sha256(q("pinSHA256") or q("pinsha256"))
        if pin_hex:
            tls_settings["pinnedPeerCertSha256"] = pin_hex

        stream = {
            "network": "hysteria",
            "security": "tls",
            "tlsSettings": tls_settings,
            "hysteriaSettings": {"version": 2, "auth": auth},
        }
        if q("obfs") == "salamander" and q("obfs-password"):
            stream["finalmask"] = {
                "udp": [{"type": "salamander", "settings": {"password": q("obfs-password")}}]
            }

        return {
            "tag": tag,
            "protocol": "hysteria",
            "settings": {"version": 2, "address": host, "port": int(port)},
            "streamSettings": stream,
        }

    return None


def _trim_outbounds(outbounds: list[dict]) -> list[dict]:
    """
    Держим конфиг в бюджете клиента (iOS-расширение Happ падает по памяти на больших
    списках). Свои серверы (prem-) не выбрасываем никогда, режем только публичные.
    """
    if len(outbounds) <= MAX_OUTBOUNDS_PER_CONFIG:
        return outbounds
    prem = [o for o in outbounds if o.get("tag", "").startswith("prem-")]
    public = [o for o in outbounds if not o.get("tag", "").startswith("prem-")]
    room = max(0, MAX_OUTBOUNDS_PER_CONFIG - len(prem))
    return prem + public[:room]


def _make_xray_group_config(remarks: str, outbounds: list[dict]) -> dict:
    outbounds = _trim_outbounds(list(outbounds))
    config: dict = {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }
        ],
        "outbounds": outbounds + [{"tag": "direct", "protocol": "freedom"}],
    }

    if len(outbounds) >= 2:
        prefixes = [p for p in ("prem-", "pub-") if any(o["tag"].startswith(p) for o in outbounds)]
        config["burstObservatory"] = {
            "subjectSelector": prefixes,
            "pingConfig": {
                "destination": "https://cp.cloudflare.com/generate_204",
                "connectivity": "http://cp.cloudflare.com/generate_204",
                "interval": BURST_PING_INTERVAL,
                "sampling": BURST_PING_SAMPLING,
                "timeout": BURST_PING_TIMEOUT,
            },
        }
        config["routing"] = {
            "domainStrategy": "AsIs",
            "balancers": [
                {
                    "tag": "auto-balancer",
                    "selector": prefixes,
                    "fallbackTag": outbounds[0]["tag"],
                    "strategy": {
                        "type": "leastLoad",
                        "settings": {
                            "costs": [
                                {"regexp": False, "match": "prem-", "value": 0.05},
                                {"regexp": False, "match": "pub-", "value": 3.0},
                            ],
                            "expected": 1,
                            "maxRTT": LEAST_LOAD_MAX_RTT,
                            "tolerance": LEAST_LOAD_TOLERANCE,
                            "baselines": ["150ms", "350ms", "700ms"],
                        },
                    },
                }
            ],
            "rules": [
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "balancerTag": "auto-balancer",
                }
            ],
        }
    else:
        config["routing"] = {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": outbounds[0]["tag"],
                }
            ],
        }

    return config


def build_xray_country_grouped_payload(
    subscription: Subscription,
    inbounds: Iterable[NodeInbound],
    public_items: Iterable[dict],
    network_type: str | None = None,
) -> str:
    """
    Собирает массив Xray JSON для Happ / INCY:
    1) «⭐ Автовыбор» (наши премиум-ноды + лучшие публичные по странам, leastLoad + costs).
    2) Страны по порядку приоритета (NL -> DE -> SE -> FI -> LV -> остальные -> Прочие),
       внутри каждой страны — автовыбор по всем ее серверам (с приоритетом наших).
    """
    inbound_list = list(inbounds)
    pub_list = list(public_items)

    # Сначала строим пулы по странам
    country_groups: dict[str, list[dict]] = {}

    # Порядок: живые и быстрые серверы первыми. Первый outbound становится fallbackTag,
    # поэтому пока balancer не набрал статистику, трафик идет через заведомо живой сервер.
    ordered_inbounds = sorted(
        inbound_list,
        key=lambda inb: _inbound_preference_key(inb, network_type),
    )
    prem_outbounds_all: list[dict] = []
    for idx, inb in enumerate(ordered_inbounds):
        cc = (inb.node.country_code or "").upper().strip() or "ZZ"
        out = _inbound_to_xray_outbound(subscription, inb, tag=f"prem-{idx}")
        if out is None:
            continue
        prem_outbounds_all.append(out)
        country_groups.setdefault(cc, []).append(
            _inbound_to_xray_outbound(subscription, inb, tag=f"prem-{len(country_groups.get(cc, []))}")
        )

    pub_outbounds_by_country: dict[str, list[dict]] = {}
    for item in pub_list:
        cc = (item.get("country_code") or "").upper().strip() or "ZZ"
        cur_list = country_groups.setdefault(cc, [])
        pub_idx = sum(1 for o in cur_list if o["tag"].startswith("pub-"))
        out = _uri_to_xray_outbound(item["uri"], tag=f"pub-{pub_idx}")
        if out is None:
            continue
        cur_list.append(out)
        pub_outbounds_by_country.setdefault(cc, []).append(out)

    if not country_groups:
        return "[]"

    configs: list[dict] = []

    # 1. Глобальный «⭐ Автовыбор»: наши премиум-ноды (до 10) + публичные из топ-стран,
    #    пока не упремся в MAX_AUTO_OUTBOUNDS
    auto_outbounds: list[dict] = []
    for i, out in enumerate(prem_outbounds_all[:10]):
        cloned = dict(out)
        cloned["tag"] = f"prem-{i}"
        auto_outbounds.append(cloned)

    sorted_country_codes = sorted(country_groups.keys(), key=get_country_rank)

    pub_counter = 0
    round_idx = 0
    while len(auto_outbounds) < MAX_AUTO_OUTBOUNDS and round_idx < 3:
        added_any = False
        for cc in sorted_country_codes:
            if len(auto_outbounds) >= MAX_AUTO_OUTBOUNDS:
                break
            cc_pubs = pub_outbounds_by_country.get(cc) or []
            if round_idx < len(cc_pubs):
                cloned = dict(cc_pubs[round_idx])
                cloned["tag"] = f"pub-{pub_counter}"
                auto_outbounds.append(cloned)
                pub_counter += 1
                added_any = True
        if not added_any:
            break
        round_idx += 1

    if auto_outbounds:
        configs.append(_make_xray_group_config(remarks="⭐ Автовыбор", outbounds=auto_outbounds))

    # 2. Конфиги по странам: сначала страны, где есть наши серверы (их терять нельзя),
    #    затем публичные по приоритету, пока не упремся в бюджет профилей клиента.
    our_countries = {
        cc
        for cc, items in country_groups.items()
        if any(item.get("tag", "").startswith("prem-") for item in items)
    }
    config_order = sorted(
        (cc for cc in sorted_country_codes if country_groups[cc]),
        key=lambda cc: (0 if cc in our_countries else 1, get_country_rank(cc)),
    )

    budget = MAX_XRAY_CONFIGS - len(configs)
    for cc in config_order:
        if budget <= 0:
            break
        configs.append(
            _make_xray_group_config(
                remarks=get_country_display(cc),
                outbounds=country_groups[cc],
            )
        )
        budget -= 1

    return json.dumps(configs, ensure_ascii=False)


PROTOCOL_SHORT_LABELS = {
    NodeInbound.Protocol.VLESS_REALITY: "Reality",
    NodeInbound.Protocol.VLESS_WS: "WS",
    NodeInbound.Protocol.HYSTERIA2: "Hy2",
}


def _flat_remark(inbound: NodeInbound) -> str:
    proto = PROTOCOL_SHORT_LABELS.get(inbound.protocol, inbound.protocol)
    return f"{_build_label(inbound)} · {proto} · {inbound.connect_host}:{inbound.connect_port}"


def build_xray_flat_payload(items: Iterable[tuple[NodeInbound, str]]) -> str:
    """
    Плоский список Xray JSON для админской/тестовой подписки: один конфиг на один инбаунд,
    без balancer и без observatory. Клиент проверяет и подключает сервер напрямую,
    поэтому такой список показывает реальное состояние серверов, а не работу balancer.

    items: пары (инбаунд, Xray UUID). В админской подписке используется probe-клиент ноды.
    """
    configs: list[dict] = []
    for inbound, xray_uuid in items:
        target = SimpleNamespace(xray_uuid=xray_uuid)
        outbound = _inbound_to_xray_outbound(target, inbound, tag="proxy")
        if outbound is None:
            continue
        configs.append(
            _make_xray_group_config(remarks=_flat_remark(inbound), outbounds=[outbound])
        )
    return json.dumps(configs, ensure_ascii=False)