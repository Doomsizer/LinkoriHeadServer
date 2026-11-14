import base64
import hashlib
from types import SimpleNamespace

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


class ProbeNodesListView(APIView):
    """
    Отдает стенду список наших включенных инбаундов с готовыми URI
    под сервисным (админ) пользователем 3x-ui.
    """

    authentication_classes = []
    permission_classes = [HasProbeToken]

    def get(self, request):
        queryset = (
            NodeInbound.objects.select_related("node")
            .filter(is_enabled=True, node__is_enabled=True)
            .order_by("node__priority", "id")
        )

        protocol = request.query_params.get("protocol", "").strip()
        if protocol:
            queryset = queryset.filter(protocol=protocol)

        if request.query_params.get("only_live") == "1":
            queryset = queryset.filter(
                health_status__in=[
                    NodeInbound.HealthStatus.ONLINE,
                    NodeInbound.HealthStatus.DEGRADED,
                ]
            )

        device_os = request.query_params.get("device_os", "").strip()
        user_agent = request.query_params.get("user_agent", "").strip()

        nodes_payload = []
        skipped = []

        for inbound in queryset:
            extra = inbound.extra_params or {}
            xray_uuid = str(extra.get("probe_xray_uuid") or settings.PROBE_XRAY_UUID or "").strip()
            ss_password = str(
                extra.get("probe_ss_password") or settings.PROBE_SS_PASSWORD or ""
            ).strip()

            if inbound.protocol == NodeInbound.Protocol.SS and not ss_password:
                skipped.append({"inbound_id": inbound.id, "reason": "missing_probe_ss_password"})
                continue
            if inbound.protocol != NodeInbound.Protocol.SS and not xray_uuid:
                skipped.append({"inbound_id": inbound.id, "reason": "missing_probe_xray_uuid"})
                continue

            probe_sub = SimpleNamespace(xray_uuid=xray_uuid, ss_password=ss_password)
            uri = build_inbound_uri(
                subscription=probe_sub,
                inbound=inbound,
                device_os=device_os,
                user_agent=user_agent,
            )

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
                "count": len(nodes_payload),
                "nodes": nodes_payload,
                "skipped": skipped,
            },
            status=status.HTTP_200_OK,
        )


class ProbeReportView(APIView):
    """
    Принимает от стенда рабочие ссылки конфигов.
    Если список повторился с прошлым отчетом — подтверждает актуальность.
    Если изменился — деактивирует пропавшие старые ссылки и сохраняет новые.
    """

    authentication_classes = []
    permission_classes = [HasProbeToken]

    def post(self, request):
        serializer = ProbeReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source = serializer.validated_data["source"]
        new_configs = sorted(serializer.validated_data["configs"])
        own_results = serializer.validated_data.get("own_results", [])

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

            # Опциональное обновление статусов наших инбаундов, если стенд их прислал
            updated_own_count = 0
            for item in own_results:
                new_status = (
                    NodeInbound.HealthStatus.ONLINE
                    if item["is_alive"]
                    else NodeInbound.HealthStatus.OFFLINE
                )
                updated_own_count += NodeInbound.objects.filter(id=item["inbound_id"]).update(
                    health_status=new_status,
                    last_latency_ms=item.get("latency_ms"),
                    last_checked_at=now,
                )

        return Response(
            {
                "status": "ok",
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
    """Возвращает текущие рабочие конфиги из последнего отчета стенда."""

    authentication_classes = []
    permission_classes = [HasProbeToken]

    def get(self, request):
        source = request.query_params.get("source", "default").strip()
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