import base64
from collections.abc import Iterable
from urllib.parse import quote, urlencode

from billing.models import Subscription
from nodes.models import NodeInbound

IOS_USER_AGENT_HINTS = (
    "shadowrocket",
    "streisand",
    "v2box",
    "foxray",
    "npv",
    "loon",
    "quantumult",
    "potatso",
    "ios",
    "iphone",
    "ipad",
)


def is_ios_client(device_os: str = "", user_agent: str = "") -> bool:
    if device_os and device_os.strip().lower() == "ios":
        return True
    ua = (user_agent or "").lower()
    return any(hint in ua for hint in IOS_USER_AGENT_HINTS)


def should_use_sip002_for_ss(
    method: str,
    device_os: str = "",
    user_agent: str = "",
    extra_params: dict | None = None,
) -> bool:
    params = extra_params or {}
    if params.get("force_sip002") is True:
        return True
    if params.get("force_sip022") is True:
        return False
    # Классические AEAD-шифры всегда кодируются по SIP002 (base64)
    if not method.startswith("2022-"):
        return True
    # Для iOS-клиентов (Shadowrocket, V2Box, Streisand и т.д.) отдаем SIP002
    return is_ios_client(device_os=device_os, user_agent=user_agent)


def _format_host(host: str) -> str:
    # Оборачиваем IPv6-адрес в квадратные скобки, если они не заданы
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _build_remark(inbound: NodeInbound) -> str:
    flag = inbound.node.flag_emoji.strip()
    name = inbound.display_name.strip()
    label = f"{flag} {name}".strip() if flag else name
    return quote(label, safe="")


def _clean_query(params: dict[str, str | int | None]) -> str:
    filtered = {k: str(v) for k, v in params.items() if v is not None and v != ""}
    return urlencode(filtered)



def build_vless_reality_uri(subscription: Subscription, inbound: NodeInbound) -> str:
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
    remark = _build_remark(inbound)
    return f"vless://{subscription.xray_uuid}@{host}:{inbound.connect_port}?{query}#{remark}"


def build_vless_ws_uri(subscription: Subscription, inbound: NodeInbound) -> str:
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
    remark = _build_remark(inbound)
    return f"vless://{subscription.xray_uuid}@{host}:{inbound.connect_port}?{query}#{remark}"


def build_hysteria2_uri(subscription: Subscription, inbound: NodeInbound) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    auth = quote(str(subscription.xray_uuid), safe="")

    insecure = extra.get("insecure")
    if isinstance(insecure, bool):
        insecure = "1" if insecure else "0"

    query = _clean_query(
        {
            "sni": extra.get("sni", inbound.connect_host),
            "alpn": extra.get("alpn", ""),
            "insecure": insecure,
            "obfs": extra.get("obfs", ""),
            "obfs-password": extra.get("obfs_password", ""),
            "pinSHA256": extra.get("pin_sha256", ""),
            "mport": extra.get("mport", ""),
        }
    )
    remark = _build_remark(inbound)
    qs = f"?{query}" if query else ""
    return f"hysteria2://{auth}@{host}:{inbound.connect_port}/{qs}#{remark}"


def build_ss_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    device_os: str = "",
    user_agent: str = "",
) -> str:
    extra = inbound.extra_params or {}
    host = _format_host(inbound.connect_host)
    method = extra.get("method", "2022-blake3-aes-256-gcm")
    server_psk = extra.get("server_psk", "")

    # Если 2022-blake3-aes-128-gcm требует 16-байтный ключ, можно обрезать/передать отдельный ключ;
    # по умолчанию ss_password хранит 32-байтный ключ в base64 для aes-256/chacha20.
    user_psk = subscription.ss_password
    password = f"{server_psk}:{user_psk}" if server_psk else user_psk

    use_sip002 = should_use_sip002_for_ss(
        method=method,
        device_os=device_os,
        user_agent=user_agent,
        extra_params=extra,
    )

    if use_sip002:
        raw_creds = f"{method}:{password}".encode("utf-8")
        userinfo = base64.urlsafe_b64encode(raw_creds).decode("ascii").rstrip("=")
    else:
        userinfo = f"{quote(method, safe='')}:{quote(password, safe='')}"

    plugin = extra.get("plugin", "")
    qs = f"/?{urlencode({'plugin': plugin})}" if plugin else ""
    remark = _build_remark(inbound)
    return f"ss://{userinfo}@{host}:{inbound.connect_port}{qs}#{remark}"


def build_inbound_uri(
    subscription: Subscription,
    inbound: NodeInbound,
    device_os: str = "",
    user_agent: str = "",
) -> str:
    protocol = inbound.protocol
    if protocol == NodeInbound.Protocol.VLESS_REALITY:
        return build_vless_reality_uri(subscription, inbound)
    if protocol == NodeInbound.Protocol.VLESS_WS:
        return build_vless_ws_uri(subscription, inbound)
    if protocol == NodeInbound.Protocol.HYSTERIA2:
        return build_hysteria2_uri(subscription, inbound)
    if protocol == NodeInbound.Protocol.SS:
        return build_ss_uri(
            subscription,
            inbound,
            device_os=device_os,
            user_agent=user_agent,
        )
    raise ValueError(f"Неподдерживаемый протокол инбаунда: {protocol}")


def build_subscription_payload(
    subscription: Subscription,
    inbounds: Iterable[NodeInbound],
    device_os: str = "",
    user_agent: str = "",
) -> str:
    uris = [
        build_inbound_uri(
            subscription=subscription,
            inbound=inbound,
            device_os=device_os,
            user_agent=user_agent,
        )
        for inbound in inbounds
    ]
    raw_text = "\n".join(uris)
    return base64.b64encode(raw_text.encode("utf-8")).decode("ascii")
