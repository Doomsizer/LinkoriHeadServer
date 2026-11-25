import json
import logging
import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from django.db import transaction

from .models import NodeInbound, VpnNode

logger = logging.getLogger(__name__)

PROBE_ADMIN_EMAIL = "linkori_probe_admin"


class XuiSyncError(Exception):
    pass


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    disabled: int = 0
    skipped: int = 0
    probe_uuid: str = ""


def _clean_node_label(node_name: str) -> str:
    cleaned = re.sub(r"[\[\(]\s*\d+\s*[\]\)]", "", node_name)
    cleaned = re.sub(r"\d+", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -_[]()")
    return cleaned or node_name.strip()


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


def _build_auth_headers(node: VpnNode) -> dict[str, str]:
    token = node.panel_api_token.strip()
    if not token:
        raise XuiSyncError(f"У ноды «{node.name}» не задан panel_api_token")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _extract_pin_sha256(tls: dict, tls_inner: dict, ext: dict) -> str:
    raw = (
        ext.get("pinnedPeerCertSha256")
        or ext.get("pinSHA256")
        or tls_inner.get("pinnedPeerCertSha256")
        or tls.get("pinnedPeerCertSha256")
        or ""
    )
    if isinstance(raw, list):
        for item in raw:
            cleaned = str(item).strip()
            if cleaned:
                return cleaned
        return ""
    return str(raw).strip()


def _extract_hy2_obfs(stream: dict) -> tuple[str, str]:
    hy2 = stream.get("hysteriaSettings") or {}
    obfs = str(hy2.get("obfs") or "").strip()
    obfs_password = str(hy2.get("obfsPassword") or "").strip()
    if obfs:
        return obfs, obfs_password

    finalmask = stream.get("finalmask") or {}
    udp_masks = finalmask.get("udp") or []
    if isinstance(udp_masks, list):
        for mask in udp_masks:
            if not isinstance(mask, dict):
                continue
            if str(mask.get("type", "")).lower() == "salamander":
                mask_settings = mask.get("settings") or {}
                pwd = str(mask_settings.get("password") or "").strip()
                if pwd:
                    return "salamander", pwd
    return "", ""


def fetch_xui_inbounds(node: VpnNode, timeout: float = 10.0) -> list[dict]:
    base_url = _normalize_panel_base_url(node.panel_url)
    list_url = f"{base_url}/panel/api/inbounds/list"
    headers = _build_auth_headers(node)

    try:
        with httpx.Client(
            timeout=timeout,
            verify=node.panel_verify_ssl,
            follow_redirects=True,
        ) as client:
            resp = client.get(list_url, headers=headers)
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

    display_name = f"[Pr 👑] {_clean_node_label(node.name)}"
    is_enabled = bool(raw_inbound.get("enable", True))

    # 1. VLESS Reality (TCP / RAW / gRPC)
    if xui_protocol == "vless" and security == "reality":
        reality = stream.get("realitySettings") or {}
        reality_inner = reality.get("settings") or {}
        server_names = reality.get("serverNames") or []
        short_ids = reality.get("shortIds") or []
        clients = settings_data.get("clients") or []
        first_client = clients[0] if isinstance(clients, list) and clients else {}

        net_type = "tcp" if network in ("tcp", "raw", "") else network
        flow = str(first_client.get("flow", "")).strip()
        if net_type == "grpc":
            flow = ""
        elif not flow and net_type == "tcp":
            flow = "xtls-rprx-vision"

        extra_params: dict = {
            "type": net_type,
            "pbk": str(reality_inner.get("publicKey") or reality.get("publicKey") or "").strip(),
            "fp": str(
                reality_inner.get("fingerprint") or reality.get("fingerprint") or "chrome"
            ).strip(),
            "sni": str(server_names[0]).strip() if server_names else "",
            "sid": str(short_ids[0]).strip() if short_ids else "",
            "spx": str(reality_inner.get("spiderX") or reality.get("spiderX") or "/").strip(),
            "flow": flow,
        }

        if net_type == "grpc":
            grpc = stream.get("grpcSettings") or {}
            extra_params["service_name"] = str(grpc.get("serviceName") or "").strip()
            extra_params["multi_mode"] = bool(grpc.get("multiMode", False))
            extra_params["authority"] = str(grpc.get("authority") or "").strip()

        return {
            "xui_inbound_id": int(xui_id),
            "protocol": NodeInbound.Protocol.VLESS_REALITY,
            "display_name": display_name,
            "connect_host": str(node.ip_address),
            "connect_port": int(ext_port) if ext_port else raw_port,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    # 2. VLESS WS (через Cloudflare, внешний порт всегда 443)
    if xui_protocol == "vless" and network == "ws":
        ws = stream.get("wsSettings") or {}
        ws_headers = ws.get("headers") or {}
        tls = stream.get("tlsSettings") or {}
        tls_inner = tls.get("settings") or {}

        sni = str(tls.get("serverName") or tls_inner.get("serverName") or "").strip()
        ws_host = str(
            ws.get("host") or ws_headers.get("Host") or ws_headers.get("host") or ""
        ).strip()

        connect_host = sni or ws_host or ext_dest or str(node.ip_address)
        path = str(ws.get("path") or "/").strip() or "/"

        alpn_raw = tls.get("alpn") or ["http/1.1"]
        alpn = ",".join(str(x) for x in alpn_raw) if isinstance(alpn_raw, list) else str(alpn_raw)

        client_security = (
            "tls" if (security in ("tls", "none") or ext_force_tls == "tls") else security
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
            "connect_port": 443,
            "extra_params": extra_params,
            "is_enabled": is_enabled,
        }

    # 3. Hysteria 2
    if xui_protocol in ("hysteria", "hysteria2"):
        tls = stream.get("tlsSettings") or {}
        tls_inner = tls.get("settings") or {}

        alpn_raw = tls.get("alpn") or ["h3"]
        alpn = ",".join(str(x) for x in alpn_raw) if isinstance(alpn_raw, list) else str(alpn_raw)
        insecure = bool(tls_inner.get("allowInsecure") or tls.get("allowInsecure"))
        pin_sha256 = _extract_pin_sha256(tls=tls, tls_inner=tls_inner, ext=ext)
        obfs, obfs_password = _extract_hy2_obfs(stream)

        extra_params = {
            "sni": str(tls.get("serverName") or tls_inner.get("serverName") or "").strip(),
            "alpn": alpn,
            "insecure": insecure,
            "pin_sha256": pin_sha256,
            "obfs": obfs,
            "obfs_password": obfs_password,
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

    return None


def _get_target_inbound_ids(node: VpnNode, raw_inbounds: list[dict]) -> list[int]:
    target_inbound_ids: list[int] = []
    for raw in raw_inbounds:
        if not raw.get("enable", True):
            continue
        parsed = parse_xui_inbound(node, raw)
        if parsed is not None:
            target_inbound_ids.append(parsed["xui_inbound_id"])
    return target_inbound_ids


def _node_client_flow(raw_inbounds: list[dict]) -> str:
    """
    flow=xtls-rprx-vision нужен только при наличии чистого TCP Reality.
    При gRPC / WS / Hysteria 2 flow должен быть пустым.
    """
    for raw in raw_inbounds:
        if not raw.get("enable", True):
            continue
        if str(raw.get("protocol", "")).lower().strip() != "vless":
            continue
        stream = _parse_json_field(raw.get("streamSettings"))
        network = str(stream.get("network", "tcp")).lower().strip()
        security = str(stream.get("security", "none")).lower().strip()
        if security == "reality" and network in ("tcp", "raw", ""):
            return "xtls-rprx-vision"
    return ""


def _get_xui_client(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    node_name: str,
    email: str,
) -> tuple[dict | None, set[int]]:
    email_q = quote(email, safe="")
    get_url = f"{base_url}/panel/api/clients/get/{email_q}"
    try:
        get_resp = client.get(get_url, headers=headers)
    except httpx.HTTPError as exc:
        raise XuiSyncError(f"Ошибка проверки клиента {email} на «{node_name}»: {exc}") from exc

    if get_resp.status_code == 404:
        return None, set()
    if get_resp.status_code != 200:
        raise XuiSyncError(
            f"Неожиданный статус {get_resp.status_code} от {get_url} на «{node_name}»"
        )

    try:
        get_data = get_resp.json()
    except ValueError as exc:
        raise XuiSyncError(f"Некорректный JSON от {get_url} на «{node_name}»") from exc

    if not get_data.get("success") or not isinstance(get_data.get("obj"), dict):
        return None, set()

    obj = get_data["obj"]
    raw_ids = obj.get("inboundIds") or []
    return obj, {int(i) for i in raw_ids}


def _update_xui_client(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    node_name: str,
    email: str,
    current_client: dict,
    target_uuid: str,
    client_flow: str,
    enable: bool,
    expiry_time_ms: int,
    total_gb_bytes: int,
    tg_id_int: int,
):
    email_q = quote(email, safe="")
    # ВАЖНО: в model.Client у 3x-ui поле для UUID называется "id" (строка UUID)
    merged_client = dict(current_client)
    merged_client.pop("allowedIPs", None)
    merged_client["id"] = target_uuid
    merged_client["uuid"] = target_uuid
    merged_client["auth"] = target_uuid
    merged_client["email"] = email
    merged_client["flow"] = client_flow
    merged_client["enable"] = bool(enable)
    merged_client["expiryTime"] = int(expiry_time_ms)
    merged_client["totalGB"] = int(total_gb_bytes)
    merged_client["tgId"] = tg_id_int
    merged_client.setdefault("limitIp", 0)

    update_url = f"{base_url}/panel/api/clients/update/{email_q}"
    try:
        upd_resp = client.post(update_url, headers=headers, json=merged_client)
        upd_resp.raise_for_status()
        upd_data = upd_resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise XuiSyncError(f"Ошибка clients/update ({email}) на «{node_name}»: {exc}") from exc

    if not upd_data.get("success"):
        raise XuiSyncError(
            f"3x-ui отклонила clients/update ({email}) на «{node_name}»: "
            f"{upd_data.get('msg', 'unknown')}"
        )


def ensure_probe_admin_client_on_panel(
    node: VpnNode,
    target_inbound_ids: list[int],
    client_flow: str = "",
    timeout: float = 10.0,
) -> uuid.UUID | None:
    if not target_inbound_ids:
        return node.probe_xray_uuid

    base_url = _normalize_panel_base_url(node.panel_url)
    headers = _build_auth_headers(node)
    email_q = quote(PROBE_ADMIN_EMAIL, safe="")

    with httpx.Client(
        timeout=timeout,
        verify=node.panel_verify_ssl,
        follow_redirects=True,
    ) as client:
        existing_obj, existing_inbound_ids = _get_xui_client(
            client, base_url, headers, node.name, PROBE_ADMIN_EMAIL
        )

        if existing_obj is None:
            admin_uuid = node.probe_xray_uuid or uuid.uuid4()
            admin_uuid_str = str(admin_uuid)
            add_url = f"{base_url}/panel/api/clients/add"
            payload = {
                "client": {
                    "id": admin_uuid_str,
                    "auth": admin_uuid_str,
                    "email": PROBE_ADMIN_EMAIL,
                    "flow": client_flow,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "limitIp": 0,
                    "enable": True,
                    "tgId": 0,
                },
                "inboundIds": target_inbound_ids,
            }
            try:
                add_resp = client.post(add_url, headers=headers, json=payload)
                add_resp.raise_for_status()
                add_data = add_resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise XuiSyncError(
                    f"Ошибка создания админ-клиента на «{node.name}»: {exc}"
                ) from exc

            if not add_data.get("success"):
                raise XuiSyncError(
                    f"3x-ui отклонила создание админ-клиента на «{node.name}»: "
                    f"{add_data.get('msg', 'unknown')}"
                )

            created_obj, _ = _get_xui_client(
                client, base_url, headers, node.name, PROBE_ADMIN_EMAIL
            )
            if created_obj is not None:
                cur = created_obj.get("client") or {}
                if (
                    str(cur.get("uuid") or "").lower() != admin_uuid_str.lower()
                    or str(cur.get("flow") or "") != client_flow
                ):
                    _update_xui_client(
                        client=client,
                        base_url=base_url,
                        headers=headers,
                        node_name=node.name,
                        email=PROBE_ADMIN_EMAIL,
                        current_client=cur,
                        target_uuid=admin_uuid_str,
                        client_flow=client_flow,
                        enable=True,
                        expiry_time_ms=0,
                        total_gb_bytes=0,
                        tg_id_int=0,
                    )
            return admin_uuid

        current_client = existing_obj.get("client") or {}
        panel_uuid_str = str(current_client.get("uuid") or "").strip()
        try:
            resolved_uuid = (
                uuid.UUID(panel_uuid_str)
                if panel_uuid_str
                else (node.probe_xray_uuid or uuid.uuid4())
            )
        except ValueError:
            resolved_uuid = node.probe_xray_uuid or uuid.uuid4()

        target_uuid_str = str(node.probe_xray_uuid or resolved_uuid)
        resolved_uuid = uuid.UUID(target_uuid_str)

        needs_update = (
            not current_client.get("enable", True)
            or str(current_client.get("flow") or "") != client_flow
            or panel_uuid_str.lower() != target_uuid_str.lower()
            or str(current_client.get("auth") or "").lower() != target_uuid_str.lower()
        )
        if needs_update:
            _update_xui_client(
                client=client,
                base_url=base_url,
                headers=headers,
                node_name=node.name,
                email=PROBE_ADMIN_EMAIL,
                current_client=current_client,
                target_uuid=target_uuid_str,
                client_flow=client_flow,
                enable=True,
                expiry_time_ms=0,
                total_gb_bytes=0,
                tg_id_int=0,
            )

        missing_ids = [i for i in target_inbound_ids if i not in existing_inbound_ids]
        if missing_ids:
            attach_url = f"{base_url}/panel/api/clients/{email_q}/attach"
            try:
                att_resp = client.post(
                    attach_url,
                    headers=headers,
                    json={"inboundIds": missing_ids},
                )
                att_resp.raise_for_status()
                att_data = att_resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise XuiSyncError(
                    f"Ошибка привязки админ-клиента на «{node.name}»: {exc}"
                ) from exc

            if not att_data.get("success"):
                raise XuiSyncError(
                    f"3x-ui отклонила attach админ-клиента на «{node.name}»: "
                    f"{att_data.get('msg', 'unknown')}"
                )

        return resolved_uuid


@transaction.atomic
def sync_node_inbounds(node: VpnNode) -> SyncResult:
    raw_inbounds = fetch_xui_inbounds(node)
    result = SyncResult()
    seen_xui_ids: list[int] = []
    enabled_xui_ids: list[int] = []

    for raw in raw_inbounds:
        parsed = parse_xui_inbound(node, raw)
        if parsed is None:
            result.skipped += 1
            continue

        xui_id = parsed.pop("xui_inbound_id")
        seen_xui_ids.append(xui_id)
        if parsed["is_enabled"]:
            enabled_xui_ids.append(xui_id)

        existing = NodeInbound.objects.filter(node=node, xui_inbound_id=xui_id).first()
        if existing is None:
            NodeInbound.objects.create(node=node, xui_inbound_id=xui_id, **parsed)
            result.created += 1
        else:
            old_extra = existing.extra_params or {}
            new_extra = parsed["extra_params"]
            if "probe_xray_uuid" in old_extra and "probe_xray_uuid" not in new_extra:
                new_extra["probe_xray_uuid"] = old_extra["probe_xray_uuid"]

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

    stale_qs = NodeInbound.objects.filter(node=node, is_enabled=True)
    if seen_xui_ids:
        stale_qs = stale_qs.exclude(xui_inbound_id__in=seen_xui_ids)
    result.disabled = stale_qs.update(is_enabled=False)

    probe_ids = enabled_xui_ids or seen_xui_ids
    client_flow = _node_client_flow(raw_inbounds)
    if probe_ids:
        resolved_uuid = ensure_probe_admin_client_on_panel(
            node, probe_ids, client_flow=client_flow
        )
        if resolved_uuid and node.probe_xray_uuid != resolved_uuid:
            node.probe_xray_uuid = resolved_uuid
            node.save(update_fields=["probe_xray_uuid"])
        if resolved_uuid:
            result.probe_uuid = str(resolved_uuid)
    elif node.probe_xray_uuid:
        result.probe_uuid = str(node.probe_xray_uuid)

    return result


def _sync_single_user_on_open_client(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    node: VpnNode,
    target_inbound_ids: list[int],
    client_flow: str,
    user,
    expires_at_ms: int = 0,
    enable: bool = True,
    total_gb_bytes: int = 0,
) -> dict:
    user_uuid = str(user.xray_uuid)
    tg_id_int = int(user.telegram_id) if user.telegram_id else 0
    client_email = f"tg_{user.telegram_id}" if user.telegram_id else f"user_{user.id}"
    email_q = quote(client_email, safe="")

    existing_obj, existing_inbound_ids = _get_xui_client(
        client, base_url, headers, node.name, client_email
    )

    if existing_obj is None:
        if not enable:
            return {"added": 0, "existing": 0, "attached": 0, "updated": 0}

        add_url = f"{base_url}/panel/api/clients/add"
        payload = {
            "client": {
                "id": user_uuid,
                "auth": user_uuid,
                "email": client_email,
                "flow": client_flow,
                "totalGB": int(total_gb_bytes),
                "expiryTime": int(expires_at_ms),
                "limitIp": 0,
                "enable": True,
                "tgId": tg_id_int,
            },
            "inboundIds": target_inbound_ids,
        }
        try:
            add_resp = client.post(add_url, headers=headers, json=payload)
            add_resp.raise_for_status()
            add_data = add_resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise XuiSyncError(f"Ошибка clients/add ({client_email}) на «{node.name}»: {exc}") from exc

        if not add_data.get("success"):
            raise XuiSyncError(
                f"3x-ui отклонила clients/add ({client_email}) на «{node.name}»: "
                f"{add_data.get('msg', 'unknown')}"
            )

        created_obj, _ = _get_xui_client(
            client, base_url, headers, node.name, client_email
        )
        if created_obj is not None:
            cur = created_obj.get("client") or {}
            if (
                str(cur.get("uuid") or "").lower() != user_uuid.lower()
                or str(cur.get("flow") or "") != client_flow
            ):
                _update_xui_client(
                    client=client,
                    base_url=base_url,
                    headers=headers,
                    node_name=node.name,
                    email=client_email,
                    current_client=cur,
                    target_uuid=user_uuid,
                    client_flow=client_flow,
                    enable=True,
                    expiry_time_ms=int(expires_at_ms),
                    total_gb_bytes=int(total_gb_bytes),
                    tg_id_int=tg_id_int,
                )

        return {"added": len(target_inbound_ids), "existing": 0, "attached": 0, "updated": 0}

    current_client = existing_obj.get("client") or {}
    if not isinstance(current_client, dict):
        current_client = {}

    cur_uuid = str(current_client.get("uuid") or "").lower()
    cur_auth = str(current_client.get("auth") or "").lower()
    cur_enable = bool(current_client.get("enable", False))
    cur_expiry = int(current_client.get("expiryTime") or 0)
    cur_total = int(current_client.get("totalGB") or 0)
    cur_flow = str(current_client.get("flow") or "")

    needs_update = (
        cur_uuid != user_uuid.lower()
        or cur_auth != user_uuid.lower()
        or cur_enable != bool(enable)
        or cur_expiry != int(expires_at_ms)
        or cur_total != int(total_gb_bytes)
        or cur_flow != client_flow
    )

    updated = 0
    if needs_update:
        _update_xui_client(
            client=client,
            base_url=base_url,
            headers=headers,
            node_name=node.name,
            email=client_email,
            current_client=current_client,
            target_uuid=user_uuid,
            client_flow=client_flow,
            enable=bool(enable),
            expiry_time_ms=int(expires_at_ms),
            total_gb_bytes=int(total_gb_bytes),
            tg_id_int=tg_id_int,
        )
        updated = 1

    missing_ids = [i for i in target_inbound_ids if i not in existing_inbound_ids]
    attached = 0
    if missing_ids and enable:
        attach_url = f"{base_url}/panel/api/clients/{email_q}/attach"
        try:
            att_resp = client.post(
                attach_url,
                headers=headers,
                json={"inboundIds": missing_ids},
            )
            att_resp.raise_for_status()
            att_data = att_resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise XuiSyncError(
                f"Ошибка clients/attach ({client_email}) на «{node.name}»: {exc}"
            ) from exc

        if not att_data.get("success"):
            raise XuiSyncError(
                f"3x-ui отклонила clients/attach ({client_email}) на «{node.name}»: "
                f"{att_data.get('msg', 'unknown')}"
            )
        attached = len(missing_ids)

    return {
        "added": 0,
        "existing": len(existing_inbound_ids & set(target_inbound_ids)),
        "attached": attached,
        "updated": updated,
    }


def sync_user_subscription_on_panel(
    node: VpnNode,
    user,
    expires_at_ms: int = 0,
    enable: bool = True,
    total_gb_bytes: int = 0,
    timeout: float = 10.0,
) -> dict:
    base_url = _normalize_panel_base_url(node.panel_url)
    headers = _build_auth_headers(node)
    raw_inbounds = fetch_xui_inbounds(node, timeout=timeout)
    target_inbound_ids = _get_target_inbound_ids(node, raw_inbounds)
    client_flow = _node_client_flow(raw_inbounds)

    if not target_inbound_ids:
        return {"added": 0, "existing": 0, "attached": 0, "updated": 0}

    with httpx.Client(
        timeout=timeout,
        verify=node.panel_verify_ssl,
        follow_redirects=True,
    ) as client:
        return _sync_single_user_on_open_client(
            client=client,
            base_url=base_url,
            headers=headers,
            node=node,
            target_inbound_ids=target_inbound_ids,
            client_flow=client_flow,
            user=user,
            expires_at_ms=expires_at_ms,
            enable=enable,
            total_gb_bytes=total_gb_bytes,
        )


def sync_active_subscriptions_to_node(
    node: VpnNode,
    entries: list[dict],
    timeout: float = 10.0,
) -> dict:
    base_url = _normalize_panel_base_url(node.panel_url)
    headers = _build_auth_headers(node)
    raw_inbounds = fetch_xui_inbounds(node, timeout=timeout)
    target_inbound_ids = _get_target_inbound_ids(node, raw_inbounds)
    client_flow = _node_client_flow(raw_inbounds)

    if not target_inbound_ids:
        return {"added": 0, "updated": 0, "attached": 0, "errors": 0}

    added = 0
    updated = 0
    attached = 0
    errors = 0

    with httpx.Client(
        timeout=timeout,
        verify=node.panel_verify_ssl,
        follow_redirects=True,
    ) as client:
        for entry in entries:
            try:
                res = _sync_single_user_on_open_client(
                    client=client,
                    base_url=base_url,
                    headers=headers,
                    node=node,
                    target_inbound_ids=target_inbound_ids,
                    client_flow=client_flow,
                    user=entry["user"],
                    expires_at_ms=entry["expires_at_ms"],
                    enable=True,
                    total_gb_bytes=entry["total_gb_bytes"],
                )
                if res["added"] > 0:
                    added += 1
                updated += res["updated"]
                if res["attached"] > 0:
                    attached += 1
            except XuiSyncError as exc:
                errors += 1
                logger.warning("Ошибка досинки юзера %s на %s: %s", entry["user"].id, node.name, exc)

    return {"added": added, "updated": updated, "attached": attached, "errors": errors}


def sync_user_subscription_on_all_panels(
    user,
    expires_at_ms: int = 0,
    enable: bool = True,
    total_gb_bytes: int = 0,
) -> dict:
    nodes = VpnNode.objects.filter(is_enabled=True).order_by("priority", "id")
    total_added = 0
    total_existing = 0
    total_attached = 0
    total_updated = 0
    errors: list[dict] = []

    for node in nodes:
        if not node.panel_api_token.strip():
            errors.append({"node_id": node.id, "node_name": node.name, "error": "missing_api_token"})
            continue
        try:
            res = sync_user_subscription_on_panel(
                node=node,
                user=user,
                expires_at_ms=expires_at_ms,
                enable=enable,
                total_gb_bytes=total_gb_bytes,
            )
            total_added += res["added"]
            total_existing += res["existing"]
            total_attached += res["attached"]
            total_updated += res["updated"]
        except XuiSyncError as exc:
            errors.append({"node_id": node.id, "node_name": node.name, "error": str(exc)})

    return {
        "nodes_total": nodes.count(),
        "clients_added": total_added,
        "clients_existing": total_existing,
        "clients_attached": total_attached,
        "clients_updated": total_updated,
        "errors": errors,
    }