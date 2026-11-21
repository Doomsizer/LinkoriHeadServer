import base64
from collections.abc import Iterable
from urllib.parse import quote, urlencode

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


def _clean_query(params: dict[str, str | int | None]) -> str:
    filtered = {k: str(v) for k, v in params.items() if v is not None and v != ""}
    return urlencode(filtered)


def build_vless_reality_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    remark_override: str | None = None,
) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    query = _clean_query(
        {
            "type": extra.get("type", "tcp"),
            "security": "reality",
            "pbk": extra.get("pbk", ""),
            "fp": extra.get("fp", "chrome"),
            "sni": extra.get("sni", ""),
            "sid": extra.get("sid", ""),
            "spx": extra.get("spx", "/"),
            "flow": extra.get("flow", "xtls-rprx-vision"),
        }
    )
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


def select_best_inbound(
    inbounds: list[NodeInbound],
    network_type: str | None = None,
) -> tuple[NodeInbound | None, int | None]:
    if not inbounds:
        return None, None

    def sort_key(inb: NodeInbound):
        lat = _get_inbound_latency(inb, network_type)
        return (lat is None, lat if lat is not None else 10**9, inb.node.priority, inb.id)

    best = min(inbounds, key=sort_key)
    return best, _get_inbound_latency(best, network_type)


def build_subscription_payload(
    subscription: Subscription,
    inbounds: Iterable[NodeInbound],
    device_os: str = "",
    user_agent: str = "",
    network_type: str | None = None,
) -> str:
    inbound_list = list(inbounds)
    uris: list[str] = []

    best_inbound, best_latency = select_best_inbound(inbound_list, network_type=network_type)
    if best_inbound is not None:
        best_label = (
            f"⚡ Лучший сервер ({best_latency} мс)"
            if best_latency is not None
            else "⚡ Лучший сервер"
        )
        uris.append(
            build_inbound_uri(
                subscription=subscription,
                inbound=best_inbound,
                device_os=device_os,
                user_agent=user_agent,
                remark_override=best_label,
            )
        )

    for inbound in inbound_list:
        uris.append(
            build_inbound_uri(
                subscription=subscription,
                inbound=inbound,
                device_os=device_os,
                user_agent=user_agent,
            )
        )

    raw_text = "\n".join(uris)
    return base64.b64encode(raw_text.encode("utf-8")).decode("ascii")