import base64
import json
from collections.abc import Iterable
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from billing.models import Subscription
from nodes.models import NodeInbound


def _format_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _build_remark(inbound: NodeInbound, remark_override: str | None = None) -> str:
    if remark_override:
        return quote(remark_override.strip(), safe="")
    flag = inbound.node.flag_emoji.strip()
    name = inbound.display_name.strip()
    if flag and not name.startswith(flag):
        label = f"{flag} {name}"
    else:
        label = name
    return quote(label, safe="")


def _build_plain_remark(inbound: NodeInbound) -> str:
    flag = inbound.node.flag_emoji.strip()
    name = inbound.display_name.strip()
    if flag and not name.startswith(flag):
        return f"{flag} {name}"
    return name


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
                remark_override="⚡ Лучший сервер",
            )
        )
    elif public_uris:
        uris.append(_replace_uri_remark(public_uris[0], "⚡ Лучший сервер"))

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
) -> tuple[str, dict] | None:
    extra = inbound.extra_params or {}
    host = inbound.connect_host
    port = int(inbound.connect_port)
    remark = _build_plain_remark(inbound)

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

        return remark, {
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
        return remark, {
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

        return remark, {
            "tag": tag,
            "protocol": "hysteria",
            "settings": {"version": 2, "address": host, "port": port},
            "streamSettings": stream,
        }

    return None


def _uri_to_xray_outbound(uri: str, tag: str) -> tuple[str, dict] | None:
    parsed = urlparse(uri.strip())
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None

    remark = unquote(parsed.fragment or "").strip() or f"{host}:{port}"
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

        return remark, {
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

        return remark, {
            "tag": tag,
            "protocol": "hysteria",
            "settings": {"version": 2, "address": host, "port": int(port)},
            "streamSettings": stream,
        }

    return None


def _make_xray_skeleton(
    remarks: str,
    outbounds: list[dict],
    use_auto_balancer: bool = False,
) -> dict:
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
    if use_auto_balancer:
        config["burstObservatory"] = {
            "subjectSelector": ["proxy-"],
            "pingConfig": {
                "destination": "https://www.google.com/generate_204",
                "interval": "30s",
                "sampling": 3,
                "timeout": "5s",
            },
        }
        config["routing"] = {
            "domainStrategy": "AsIs",
            "balancers": [
                {
                    "tag": "auto-balancer",
                    "selector": ["proxy-"],
                    "fallbackTag": outbounds[0]["tag"],
                    "strategy": {"type": "leastPing"},
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


def build_happ_json_payload(
    subscription: Subscription,
    inbounds: Iterable[NodeInbound],
    network_type: str | None = None,
    extra_uris: Iterable[str] = (),
) -> str:
    inbound_list = list(inbounds)
    public_uris = [u.strip() for u in extra_uris if u and u.strip()]

    best_inbound, _ = select_best_inbound(inbound_list, network_type=network_type)
    ordered_inbounds = list(inbound_list)
    if best_inbound is not None and best_inbound in ordered_inbounds:
        ordered_inbounds.remove(best_inbound)
        ordered_inbounds.insert(0, best_inbound)

    entries: list[tuple[str, dict]] = []
    idx = 0
    for inb in ordered_inbounds:
        converted = _inbound_to_xray_outbound(subscription, inb, tag=f"proxy-{idx}")
        if converted is not None:
            entries.append(converted)
            idx += 1

    for uri in public_uris:
        converted = _uri_to_xray_outbound(uri, tag=f"proxy-{idx}")
        if converted is not None:
            entries.append(converted)
            idx += 1

    if not entries:
        return "[]"

    configs: list[dict] = []

    auto_outbounds = [outbound for _, outbound in entries]
    configs.append(
        _make_xray_skeleton(
            remarks="⚡ Лучший сервер",
            outbounds=auto_outbounds,
            use_auto_balancer=True,
        )
    )

    for remark, outbound in entries:
        single_outbound = dict(outbound)
        single_outbound["tag"] = "proxy"
        configs.append(
            _make_xray_skeleton(
                remarks=remark,
                outbounds=[single_outbound],
                use_auto_balancer=False,
            )
        )

    return json.dumps(configs, ensure_ascii=False)