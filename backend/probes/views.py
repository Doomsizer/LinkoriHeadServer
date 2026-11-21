import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import urlparse

from django.conf import settings
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


def _resolve_network_type(request, route_network_type: str | None) -> tuple[str | None, str | None]:
    stand = getattr(request, "probe_stand", None)
    if route_network_type and stand is not None and stand.network_type != route_network_type:
        return None, (
            f"Токен стенда «{stand.name}» ({stand.network_type}) не подходит для "
            f"эндпоинта «{route_network_type}»"
        )
    if route_network_type:
        return route_network_type, None
    if stand is not None:
        return stand.network_type, None
    return None, None


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


def _apply_inbound_probe_result(
    inbound: NodeInbound,
    network_type: str | None,
    is_alive: bool,
    latency_ms: int | None,
    now,
):
    new_status = NodeInbound.HealthStatus.ONLINE if is_alive else NodeInbound.HealthStatus.OFFLINE
    if network_type == "lte":
        inbound.lte_health_status = new_status
        inbound.lte_latency_ms = latency_ms if is_alive else None
        _recompute_overall_inbound_status(inbound)
    elif network_type == "wifi":
        inbound.wifi_health_status = new_status
        inbound.wifi_latency_ms = latency_ms if is_alive else None
        _recompute_overall_inbound_status(inbound)
    else:
        inbound.health_status = new_status
        inbound.last_latency_ms = latency_ms if is_alive else None

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


class ProbeNodesListView(APIView):
    """
    Отдает стенду список наших включенных инбаундов с готовыми URI
    под сервисным Xray UUID. Поддерживает разделение на lte и wifi.
    """

    authentication_classes = []
    permission_classes = [HasProbeToken]
    network_type: str | None = None

    def get(self, request):
        resolved_net, err = _resolve_network_type(request, self.network_type)
        if err:
            return Response({"detail": err}, status=status.HTTP_403_FORBIDDEN)

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

        if request.query_params.get("only_live") == "1":
            if resolved_net == "lte":
                queryset = queryset.filter(
                    lte_health_status__in=[
                        NodeInbound.HealthStatus.ONLINE,
                        NodeInbound.HealthStatus.DEGRADED,
                    ]
                )
            elif resolved_net == "wifi":
                queryset = queryset.filter(
                    wifi_health_status__in=[
                        NodeInbound.HealthStatus.ONLINE,
                        NodeInbound.HealthStatus.DEGRADED,
                    ]
                )
            else:
                queryset = queryset.filter(
                    health_status__in=[
                        NodeInbound.HealthStatus.ONLINE,
                        NodeInbound.HealthStatus.DEGRADED,
                    ]
                )

        nodes_payload = []
        skipped = []

        for inbound in queryset:
            extra = inbound.extra_params or {}
            xray_uuid = str(
                stand_uuid
                or extra.get("probe_xray_uuid")
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
                "network_type": resolved_net or "all",
                "count": len(nodes_payload),
                "nodes": nodes_payload,
                "skipped": skipped,
            },
            status=status.HTTP_200_OK,
        )


class ProbeReportView(APIView):
    """
    Принимает от стенда рабочие ссылки конфигов (отдельно для lte, wifi или default).
    """

    authentication_classes = []
    permission_classes = [HasProbeToken]
    network_type: str | None = None

    def post(self, request):
        resolved_net, err = _resolve_network_type(request, self.network_type)
        if err:
            return Response({"detail": err}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProbeReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_source = serializer.validated_data.get("source", "").strip()
        source = raw_source or resolved_net or "default"
        new_configs = sorted(serializer.validated_data["configs"])
        own_results = serializer.validated_data.get("own_results", [])
        sync_own = serializer.validated_data.get("sync_own", False)

        config_hash = hashlib.sha256("\n".join(new_configs).encode("utf-8")).hexdigest()
        now = timezone.now()

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

                WorkingPublicConfig.objects.filter(source=source, is_active=True).update(
                    last_seen_at=now
                )

                changed = False
                added = []
                removed = []
                snapshot_id = prev_snapshot.id
            else:
                old_set = set(prev_snapshot.configs) if prev_snapshot else set()
                new_set = set(new_configs)

                added = sorted(new_set - old_set)
                removed = sorted(old_set - new_set)

                if removed:
                    removed_hashes = [hash_uri(u) for u in removed]
                    WorkingPublicConfig.objects.filter(
                        source=source,
                        uri_hash__in=removed_hashes,
                    ).update(is_active=False, last_seen_at=now)

                if new_configs:
                    existing_map = {
                        obj.uri_hash: obj
                        for obj in WorkingPublicConfig.objects.filter(
                            source=source,
                            uri_hash__in=[hash_uri(u) for u in new_configs],
                        )
                    }
                    to_create = []
                    to_update = []
                    for uri in new_configs:
                        u_hash = hash_uri(uri)
                        obj = existing_map.get(u_hash)
                        if obj is None:
                            scheme = uri.split("://", 1)[0].lower()[:24]
                            to_create.append(
                                WorkingPublicConfig(
                                    source=source,
                                    uri=uri,
                                    uri_hash=u_hash,
                                    protocol=scheme,
                                    is_active=True,
                                )
                            )
                        else:
                            obj.uri = uri
                            obj.is_active = True
                            obj.last_seen_at = now
                            to_update.append(obj)

                    if to_create:
                        WorkingPublicConfig.objects.bulk_create(to_create)
                    if to_update:
                        WorkingPublicConfig.objects.bulk_update(
                            to_update,
                            fields=["uri", "is_active", "last_seen_at"],
                        )

                snapshot = ProbeSnapshot.objects.create(
                    source=source,
                    config_hash=config_hash,
                    configs=new_configs,
                    added_configs=added,
                    removed_configs=removed,
                    is_changed=True,
                    total_count=len(new_configs),
                )
                changed = True
                snapshot_id = snapshot.id

            updated_own_count = 0
            if own_results:
                inbound_map = {
                    inb.id: inb
                    for inb in NodeInbound.objects.filter(
                        id__in=[item["inbound_id"] for item in own_results]
                    )
                }
                for item in own_results:
                    inb = inbound_map.get(item["inbound_id"])
                    if inb is None:
                        continue
                    _apply_inbound_probe_result(
                        inbound=inb,
                        network_type=resolved_net,
                        is_alive=item["is_alive"],
                        latency_ms=item.get("latency_ms"),
                        now=now,
                    )
                    updated_own_count += 1
            elif sync_own:
                working_endpoints = set()
                for uri in new_configs:
                    parsed = urlparse(uri)
                    if parsed.hostname and parsed.port:
                        working_endpoints.add((parsed.hostname.lower(), int(parsed.port)))

                for inb in NodeInbound.objects.filter(is_enabled=True, node__is_enabled=True):
                    is_alive = (inb.connect_host.lower(), int(inb.connect_port)) in working_endpoints
                    _apply_inbound_probe_result(
                        inbound=inb,
                        network_type=resolved_net,
                        is_alive=is_alive,
                        latency_ms=None,
                        now=now,
                    )
                    updated_own_count += 1

        return Response(
            {
                "status": "ok",
                "network_type": resolved_net or "all",
                "source": source,
                "snapshot_id": snapshot_id,
                "changed": changed,
                "active_count": len(new_configs),
                "added_count": len(added),
                "removed_count": len(removed),
                "added": added,
                "removed": removed,
                "updated_own_inbounds": updated_own_count,
            },
            status=status.HTTP_200_OK,
        )


class ProbeActiveConfigsView(APIView):
    """Возвращает собранные рабочие конфиги / подписку для LTE, Wi-Fi или по source."""

    authentication_classes = []
    permission_classes = [HasProbeToken]
    network_type: str | None = None

    def get(self, request):
        resolved_net, err = _resolve_network_type(request, self.network_type)
        if err:
            return Response({"detail": err}, status=status.HTTP_403_FORBIDDEN)

        source = request.query_params.get("source", "").strip() or resolved_net or "default"
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
                "network_type": resolved_net or "all",
                "source": source,
                "count": len(uris),
                "configs": uris,
            },
            status=status.HTTP_200_OK,
        )