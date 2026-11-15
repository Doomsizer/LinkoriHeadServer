import json
from dataclasses import dataclass

import httpx
from django.db import transaction

from .models import NodeInbound, VpnNode


class XuiSyncError(Exception):
    pass


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    disabled: int = 0
    skipped: int = 0


def _normalize_panel_base_url(panel_url: str) -> str:
    base = panel_url.strip().rstrip("/")
    if base.endswith("/panel"):
        base = base[:-6]
    return base


def _parse_json_field(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def fetch_xui_inbounds(node: VpnNode, timeout: float = 10.0) -> list[dict]:
    base_url = _normalize_panel_base_url(node.panel_url)
    list_url = f"{base_url}/panel/api/inbounds/list"

    try:
        with httpx.Client(timeout=timeout, verify=node.panel_verify_ssl, follow_redirects=True) as client:
            if node.panel_api_token.strip():
                resp = client.get(
                    list_url,
                    headers={
                        "Authorization": f"Bearer {node.panel_api_token.strip()}",
                        "Accept": "application/json",
                    },
                )
            elif node.panel_username.strip() and node.panel_password.strip():
                login_resp = client.post(
                    f"{base_url}/login",
                    json={
                        "username": node.panel_username.strip(),
                        "password": node.panel_password,
                    },
                    headers={"Accept": "application/json"},
                )
                login_resp.raise_for_status()
                login_data = login_resp.json()
                if not login_data.get("success"):
                    raise XuiSyncError(f"Ошибка входа в 3x-ui: {login_data.get('msg', 'unknown')}")
                resp = client.get(list_url, headers={"Accept": "application/json"})
            else:
                raise XuiSyncError("Не задан API-токен или логин/пароль для панели 3x-ui")

            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        raise XuiSyncError(f"Ошибка соединения с 3x-ui ({base_url}): {exc}") from exc
    except ValueError as exc:
        raise XuiSyncError(f"3x-ui вернула некорректный JSON ({base_url})") from exc

    if not payload.get("success"):
        raise XuiSyncError(f"3x-ui вернула ошибку: {payload.get('msg', 'unknown')}")

    inbounds = payload.get("obj")
    if not isinstance(inbounds, list):
        raise XuiSyncError("Поле obj в ответе 3x-ui не является списком")
    return inbounds


def parse_xui_inbound(node: VpnNode, raw_inbound: dict) -> dict | None:
    xui_protocol = str(raw_inbound.get("protocol", "")).lower().strip()
    xui_id = raw_inbound.get("id")
    if not xui_id:
        return None

    settings_data = _parse_json_field(raw_inbound.get("settings"))
    stream = _parse_json_field(raw_inbound.get("streamSettings"))

    network = str(stream.get("network", "tcp")).lower().strip()
    security = str(stream.get("security", "none")).lower().strip()

    external_proxies = stream.get("externalProxy") or []
    ext = external_proxies[0] if isinstance(external_proxies, list) and external_proxies else {}
    if not isinstance(ext, dict):
        ext = {}

    ext_dest = str(ext.get("dest", "")).strip()
    ext_port = ext.get("port")
    ext_force_tls = str(ext.get("forceTls", "")).lower().strip()

    raw_port = int(raw_inbound.get("port") or 0)
    if raw_port <= 0:
        return None

    display_name = f"Premium {node.name}"
    is_enabled = bool(raw_inbound.get("enable", True))

    # 1. VLESS Reality
    if xui_protocol == "vless" and security == "reality":
        reality = stream.get("realitySettings") or {}
        reality_inner = reality.get("settings") or {}
        server_names = reality.get("serverNames") or []
        short_ids = reality.get("shortIds") or []
        clients = settings_data.get("clients") or []
        first_client = clients[0] if isinstance(clients, list) and clients else {}

        flow = str(first_client.get("flow", "")).strip()
        if not flow and network in ("tcp", "raw", ""):
            flow = "xtls-rprx-vision"

        extra_params = {
            "type": "tcp" if network in ("tcp", "raw", "") else network,
            "pbk": str(reality_inner.get("publicKey") or reality.get("publicKey") or "").strip(),
            "fp": str(
                reality_inner.get("fingerprint") or reality.get("fingerprint") or "chrome"
            ).strip(),
            "sni": str(server_names[0]).strip() if server_names else "",
            "sid": str(short_ids[0]).strip() if short_ids else "",
            "spx": str(reality_inner.get("spiderX") or reality.get("spiderX") or "/").strip(),
            "flow": flow,
        }
        return {
            "xui_inbound_id": int(xui_id),
            "protocol": NodeInbound.Protocol.VLESS_REALITY,
            "display_name": display_name,
            "connect_host": str(node.ip_address),
            "connect_port": int(ext_port) if ext_port else raw_port,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    # 2. VLESS WS (через Cloudflare / домен)
    if xui_protocol == "vless" and network == "ws":
        ws = stream.get("wsSettings") or {}
        ws_headers = ws.get("headers") or {}
        tls = stream.get("tlsSettings") or {}
        tls_inner = tls.get("settings") or {}

        sni = str(tls.get("serverName") or tls_inner.get("serverName") or "").strip()
        ws_host = str(
            ws.get("host") or ws_headers.get("Host") or ws_headers.get("host") or ""
        ).strip()

        # Для WS хост подключения — домен (берем из sni, затем ws_host / externalProxy)
        connect_host = sni or ws_host or ext_dest or str(node.ip_address)
        connect_port = int(ext_port) if ext_port else raw_port
        path = str(ws.get("path") or "/").strip() or "/"

        alpn_raw = tls.get("alpn") or ["http/1.1"]
        alpn = ",".join(str(x) for x in alpn_raw) if isinstance(alpn_raw, list) else str(alpn_raw)

        client_security = (
            "tls"
            if (security == "tls" or ext_force_tls == "tls" or connect_port == 443)
            else security
        )

        extra_params = {
            "security": client_security,
            "path": path,
            "host": ws_host or connect_host,
            "sni": sni or connect_host,
            "fp": str(tls_inner.get("fingerprint") or tls.get("fingerprint") or "chrome").strip(),
            "alpn": alpn,
        }
        return {
            "xui_inbound_id": int(xui_id),
            "protocol": NodeInbound.Protocol.VLESS_WS,
            "display_name": display_name,
            "connect_host": connect_host,
            "connect_port": connect_port,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    # 3. Hysteria 2
    if xui_protocol in ("hysteria", "hysteria2"):
        tls = stream.get("tlsSettings") or {}
        tls_inner = tls.get("settings") or {}
        hy2 = stream.get("hysteriaSettings") or {}

        alpn_raw = tls.get("alpn") or ["h3"]
        alpn = ",".join(str(x) for x in alpn_raw) if isinstance(alpn_raw, list) else str(alpn_raw)
        insecure = bool(tls_inner.get("allowInsecure") or tls.get("allowInsecure"))

        extra_params = {
            "sni": str(tls.get("serverName") or tls_inner.get("serverName") or "").strip(),
            "alpn": alpn,
            "insecure": insecure,
            "obfs": str(hy2.get("obfs") or "").strip(),
            "obfs_password": str(hy2.get("obfsPassword") or "").strip(),
        }
        return {
            "xui_inbound_id": int(xui_id),
            "protocol": NodeInbound.Protocol.HYSTERIA2,
            "display_name": display_name,
            "connect_host": str(node.ip_address),
            "connect_port": int(ext_port) if ext_port else raw_port,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    # 4. Shadowsocks 2022
    if xui_protocol == "shadowsocks":
        method = str(settings_data.get("method", "2022-blake3-aes-256-gcm")).strip()
        server_psk = str(settings_data.get("password", "")).strip()
        extra_params = {
            "method": method,
            "server_psk": server_psk,
        }
        return {
            "xui_inbound_id": int(xui_id),
            "protocol": NodeInbound.Protocol.SS,
            "display_name": display_name,
            "connect_host": str(node.ip_address),
            "connect_port": int(ext_port) if ext_port else raw_port,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    return None


@transaction.atomic
def sync_node_inbounds(node: VpnNode) -> SyncResult:
    raw_inbounds = fetch_xui_inbounds(node)
    result = SyncResult()
    seen_xui_ids: list[int] = []

    for raw in raw_inbounds:
        parsed = parse_xui_inbound(node, raw)
        if parsed is None:
            result.skipped += 1
            continue

        xui_id = parsed.pop("xui_inbound_id")
        seen_xui_ids.append(xui_id)

        existing = NodeInbound.objects.filter(node=node, xui_inbound_id=xui_id).first()
        if existing is None:
            NodeInbound.objects.create(node=node, xui_inbound_id=xui_id, **parsed)
            result.created += 1
        else:
            # Сохраняем пользовательские probe-переопределения, если они были заданы в extra_params
            old_extra = existing.extra_params or {}
            new_extra = parsed["extra_params"]
            for key in ("probe_xray_uuid", "probe_ss_password", "force_sip002", "force_sip022"):
                if key in old_extra and key not in new_extra:
                    new_extra[key] = old_extra[key]

            existing.protocol = parsed["protocol"]
            existing.display_name = parsed["display_name"]
            existing.connect_host = parsed["connect_host"]
            existing.connect_port = parsed["connect_port"]
            existing.extra_params = new_extra
            existing.is_enabled = parsed["is_enabled"]
            existing.save(
                update_fields=[
                    "protocol",
                    "display_name",
                    "connect_host",
                    "connect_port",
                    "extra_params",
                    "is_enabled",
                ]
            )
            result.updated += 1

    # Отключаем инбаунды, которых больше нет в 3x-ui на этой ноде
    stale_qs = NodeInbound.objects.filter(node=node, is_enabled=True)
    if seen_xui_ids:
        stale_qs = stale_qs.exclude(xui_inbound_id__in=seen_xui_ids)
    result.disabled = stale_qs.update(is_enabled=False)

    return result