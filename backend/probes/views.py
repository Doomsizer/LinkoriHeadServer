import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nodes.models import NodeInbound
from sub_gateway.uri_builder import build_inbound_uri

from .models import ProbeSnapshot, WorkingPublicConfig, hash_uri
from .permissions import HasProbeToken
from .serializers import ProbeReportSerializer
from .tasks import send_probe_status_alert


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


def _extract_uri_endpoint(uri: str) -> tuple[str, str, int] | None:
    parsed = urlparse(uri)
    if not parsed.hostname or not parsed.port:
        return None
    return (_uri_protocol_family(uri), parsed.hostname.lower(), int(parsed.port))


def _recompute_overall_inbound_status(inbound: NodeInbound):
    lte = inbound.lte_health_status
    wifi = inbound.wifi_health_status
    statuses = {lte, wifi}

    if NodeInbound.HealthStatus.ONLINE in statuses:
        if (
            lte == NodeInbound.HealthStatus.ONLINE
            and wifi == NodeInbound.HealthStatus.ONLINE
        ) or NodeInbound.HealthStatus.UNKNOWN in statuses:
            inbound.health_status = NodeInbound.HealthStatus.ONLINE
        else:
            inbound.health_status = NodeInbound.HealthStatus.DEGRADED
    elif NodeInbound.HealthStatus.DEGRADED in statuses:
        inbound.health_status = NodeInbound.HealthStatus.DEGRADED
    elif statuses == {NodeInbound.HealthStatus.OFFLINE} or (
        NodeInbound.HealthStatus.OFFLINE in statuses and NodeInbound.HealthStatus.UNKNOWN in statuses
    ):
        inbound.health_status = NodeInbound.HealthStatus.OFFLINE

    latencies = [x for x in (inbound.lte_latency_ms, inbound.wifi_latency_ms) if x is not None]
    if latencies:
        inbound.last_latency_ms = min(latencies)


def _get_network_status(inbound: NodeInbound, network_type: str | None) -> str:
    if network_type == "lte":
        return inbound.lte_health_status
    if network_type == "wifi":
        return inbound.wifi_health_status
    return inbound.health_status


def _apply_inbound_probe_result(
    inbound: NodeInbound,
    network_type: str | None,
    is_alive: bool,
    latency_ms: int | None,
    now,
    keep_existing_latency: bool = False,
) -> tuple[str, str]:
    prev_status = _get_network_status(inbound, network_type)
    new_status = NodeInbound.HealthStatus.ONLINE if is_alive else NodeInbound.HealthStatus.OFFLINE

    if network_type == "lte":
        inbound.lte_health_status = new_status
        if not is_alive:
            inbound.lte_latency_ms = None
        elif latency_ms is not None or not keep_existing_latency:
            inbound.lte_latency_ms = latency_ms
        _recompute_overall_inbound_status(inbound)
    elif network_type == "wifi":
        inbound.wifi_health_status = new_status
        if not is_alive:
            inbound.wifi_latency_ms = None
        elif latency_ms is not None or not keep_existing_latency:
            inbound.wifi_latency_ms = latency_ms
        _recompute_overall_inbound_status(inbound)
    else:
        inbound.health_status = new_status
        if not is_alive:
            inbound.last_latency_ms = None
        elif latency_ms is not None or not keep_existing_latency:
            inbound.last_latency_ms = latency_ms

    inbound.last_checked_at = now
    inbound.save(
        update_fields=[
            "health_status",
            "last_latency_ms",
            "lte_health_status",
            "lte_latency_ms",
            "wifi_health_status",
            "wifi_latency_ms",
            "last_checked_at",
        ]
    )
    return prev_status, new_status


class ProbeNodesListView(APIView):
    authentication_classes = []
    permission_classes = [HasProbeToken]

    def get(self, request):
        stand = getattr(request, "probe_stand", None)
        stand_uuid = str(stand.probe_xray_uuid) if (stand and stand.probe_xray_uuid) else ""

        queryset = (
            NodeInbound.objects.select_related("node")
            .filter(is_enabled=True, node__is_enabled=True)
            .order_by("node__priority", "id")
        )

        protocol = request.query_params.get("protocol", "").strip()
        if protocol:
            queryset = queryset.filter(protocol=protocol)

        nodes_payload = []
        skipped = []

        for inbound in queryset:
            extra = inbound.extra_params or {}
            node_uuid = str(inbound.node.probe_xray_uuid or "").strip()
            xray_uuid = str(
                extra.get("probe_xray_uuid")
                or node_uuid
                or stand_uuid
                or settings.PROBE_XRAY_UUID
                or ""
            ).strip()
            if not xray_uuid:
                skipped.append({"inbound_id": inbound.id, "reason": "missing_probe_xray_uuid"})
                continue

            probe_sub = SimpleNamespace(xray_uuid=xray_uuid)
            uri = build_inbound_uri(subscription=probe_sub, inbound=inbound)

            nodes_payload.append(
                {
                    "inbound_id": inbound.id,
                    "node_id": inbound.node_id,
                    "node_name": inbound.node.name,
                    "country_code": inbound.node.country_code,
                    "protocol": inbound.protocol,
                    "display_name": inbound.display_name,
                    "connect_host": inbound.connect_host,
                    "connect_port": inbound.connect_port,
                    "health_status": inbound.health_status,
                    "lte_health_status": inbound.lte_health_status,
                    "wifi_health_status": inbound.wifi_health_status,
                    "uri": uri,
                }
            )

        out_format = request.query_params.get("format", "json").lower()
        if out_format == "plain":
            raw = "\n".join(item["uri"] for item in nodes_payload)
            return HttpResponse(raw, content_type="text/plain; charset=utf-8")
        if out_format == "base64":
            raw = "\n".join(item["uri"] for item in nodes_payload)
            encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
            return HttpResponse(encoded, content_type="text/plain; charset=utf-8")

        return Response(
            {
                "stand": stand.name if stand else None,
                "network_type": stand.network_type if stand else "all",
                "count": len(nodes_payload),
                "nodes": nodes_payload,
                "skipped": skipped,
            },
            status=status.HTTP_200_OK,
        )


class ProbeReportView(APIView):
    authentication_classes = []
    permission_classes = [HasProbeToken]

    def post(self, request):
        serializer = ProbeReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        stand = getattr(request, "probe_stand", None)
        resolved_net = serializer.validated_data.get("network_type") or (
            stand.network_type if stand else None
        )
        raw_source = serializer.validated_data.get("source", "").strip()
        source = raw_source or resolved_net or "default"

        normalized_items = serializer.validated_data["normalized_configs"]
        all_configs = sorted(item["uri"] for item in normalized_items)
        own_results = serializer.validated_data.get("own_results", [])
        sync_own = serializer.validated_data.get("sync_own", True)

        enabled_inbounds = list(
            NodeInbound.objects.select_related("node").filter(is_enabled=True, node__is_enabled=True)
        )
        own_endpoint_keys: set[tuple[str, str, int]] = set()
        for inb in enabled_inbounds:
            fam = _inbound_protocol_family(inb)
            own_endpoint_keys.add((fam, inb.connect_host.lower(), int(inb.connect_port)))
            own_endpoint_keys.add((fam, str(inb.node.ip_address).lower(), int(inb.connect_port)))

        public_items: list[dict] = []
        working_own_endpoints: set[tuple[str, str, int]] = set()
        own_latencies_by_ep: dict[tuple[str, str, int], int] = {}

        for item in normalized_items:
            uri = item["uri"]
            ep = _extract_uri_endpoint(uri)
            if ep is not None and ep in own_endpoint_keys:
                working_own_endpoints.add(ep)
                if item["latency_ms"] is not None:
                    own_latencies_by_ep[ep] = item["latency_ms"]
            else:
                public_items.append(item)

        config_hash = hashlib.sha256("\n".join(all_configs).encode("utf-8")).hexdigest()
        now = timezone.now()

        failed_alerts: list[str] = []
        recovered_alerts: list[str] = []

        def _track_alert(inb: NodeInbound, prev_st: str, new_st: str):
            net_key = resolved_net or "all"
            cd_key = f"probe_alert_cd:{inb.id}:{net_key}"
            label = f"{inb.node.name} ({inb.connect_host}:{inb.connect_port}, {inb.get_protocol_display()})"
            if new_st == NodeInbound.HealthStatus.OFFLINE:
                if prev_st != NodeInbound.HealthStatus.OFFLINE or not cache.get(cd_key):
                    cache.set(cd_key, 1, timeout=settings.PROBE_ALERT_COOLDOWN_SECONDS)
                    failed_alerts.append(label)
            elif new_st == NodeInbound.HealthStatus.ONLINE and prev_st == NodeInbound.HealthStatus.OFFLINE:
                cache.delete(cd_key)
                recovered_alerts.append(label)

        with transaction.atomic():
            prev_snapshot = (
                ProbeSnapshot.objects.select_for_update()
                .filter(source=source)
                .order_by("-created_at")
                .first()
            )

            if prev_snapshot is not None and prev_snapshot.config_hash == config_hash:
                prev_snapshot.confirmations_count = F("confirmations_count") + 1
                prev_snapshot.last_confirmed_at = now
                prev_snapshot.save(update_fields=["confirmations_count", "last_confirmed_at"])

                changed = False
                added = []
                removed = []
                snapshot_id = prev_snapshot.id
            else:
                old_set = set(prev_snapshot.configs) if prev_snapshot else set()
                new_set = set(all_configs)

                added = sorted(new_set - old_set)
                removed = sorted(old_set - new_set)

                snapshot = ProbeSnapshot.objects.create(
                    source=source,
                    config_hash=config_hash,
                    configs=all_configs,
                    added_configs=added,
                    removed_configs=removed,
                    is_changed=True,
                    total_count=len(all_configs),
                )
                changed = True
                snapshot_id = snapshot.id

            public_hashes = {hash_uri(item["uri"]) for item in public_items}
            existing_public = {
                obj.uri_hash: obj
                for obj in WorkingPublicConfig.objects.filter(source=source)
            }

            to_deactivate_ids = [
                obj.id
                for u_hash, obj in existing_public.items()
                if obj.is_active and u_hash not in public_hashes
            ]
            if to_deactivate_ids:
                WorkingPublicConfig.objects.filter(id__in=to_deactivate_ids).update(
                    is_active=False,
                    last_seen_at=now,
                )

            to_create = []
            to_update = []
            for item in public_items:
                uri = item["uri"]
                u_hash = hash_uri(uri)
                scheme = uri.split("://", 1)[0].lower()[:24]
                obj = existing_public.get(u_hash)
                if obj is None:
                    to_create.append(
                        WorkingPublicConfig(
                            source=source,
                            origin_source=item["origin_source"],
                            country_code=item["country_code"],
                            uri=uri,
                            uri_hash=u_hash,
                            protocol=scheme,
                            latency_ms=item["latency_ms"],
                            is_active=True,
                        )
                    )
                else:
                    obj.uri = uri
                    if item["origin_source"]:
                        obj.origin_source = item["origin_source"]
                    if item["country_code"]:
                        obj.country_code = item["country_code"]
                    if item["latency_ms"] is not None:
                        obj.latency_ms = item["latency_ms"]
                    obj.is_active = True
                    obj.last_seen_at = now
                    to_update.append(obj)

            if to_create:
                WorkingPublicConfig.objects.bulk_create(to_create)
            if to_update:
                WorkingPublicConfig.objects.bulk_update(
                    to_update,
                    fields=[
                        "uri",
                        "origin_source",
                        "country_code",
                        "latency_ms",
                        "is_active",
                        "last_seen_at",
                    ],
                )

            updated_own_count = 0
            if own_results:
                inbound_map = {inb.id: inb for inb in enabled_inbounds}
                for item in own_results:
                    inb = inbound_map.get(item["inbound_id"])
                    if inb is None:
                        continue
                    prev_st, new_st = _apply_inbound_probe_result(
                        inbound=inb,
                        network_type=resolved_net,
                        is_alive=item["is_alive"],
                        latency_ms=item.get("latency_ms"),
                        now=now,
                    )
                    _track_alert(inb, prev_st, new_st)
                    updated_own_count += 1
            elif sync_own:
                for inb in enabled_inbounds:
                    fam = _inbound_protocol_family(inb)
                    key_host = (fam, inb.connect_host.lower(), int(inb.connect_port))
                    key_ip = (fam, str(inb.node.ip_address).lower(), int(inb.connect_port))
                    is_alive = key_host in working_own_endpoints or key_ip in working_own_endpoints
                    lat = own_latencies_by_ep.get(key_host) or own_latencies_by_ep.get(key_ip)
                    prev_st, new_st = _apply_inbound_probe_result(
                        inbound=inb,
                        network_type=resolved_net,
                        is_alive=is_alive,
                        latency_ms=lat,
                        now=now,
                        keep_existing_latency=True,
                    )
                    _track_alert(inb, prev_st, new_st)
                    updated_own_count += 1

            if failed_alerts or recovered_alerts:
                net_label = (resolved_net or source or "all").upper()
                f_copy = list(failed_alerts)
                r_copy = list(recovered_alerts)
                transaction.on_commit(
                    lambda: send_probe_status_alert.delay(net_label, f_copy, r_copy)
                )

        return Response(
            {
                "status": "ok",
                "network_type": resolved_net or "all",
                "source": source,
                "snapshot_id": snapshot_id,
                "changed": changed,
                "active_count": len(all_configs),
                "public_active_count": len(public_items),
                "added_count": len(added),
                "removed_count": len(removed),
                "added": added,
                "removed": removed,
                "updated_own_inbounds": updated_own_count,
            },
            status=status.HTTP_200_OK,
        )


class ProbeActiveConfigsView(APIView):
    authentication_classes = []
    permission_classes = [HasProbeToken]

    def get(self, request):
        stand = getattr(request, "probe_stand", None)
        source = (
            request.query_params.get("source", "").strip()
            or request.query_params.get("network", "").strip()
            or (stand.network_type if stand else "")
            or "default"
        )
        qs = WorkingPublicConfig.objects.filter(source=source, is_active=True).order_by("id")
        uris = list(qs.values_list("uri", flat=True))

        out_format = request.query_params.get("format", "json").lower()
        if out_format == "plain":
            return HttpResponse("\n".join(uris), content_type="text/plain; charset=utf-8")
        if out_format == "base64":
            encoded = base64.b64encode("\n".join(uris).encode("utf-8")).decode("ascii")
            return HttpResponse(encoded, content_type="text/plain; charset=utf-8")

        return Response(
            {
                "source": source,
                "count": len(uris),
                "configs": uris,
            },
            status=status.HTTP_200_OK,
        )