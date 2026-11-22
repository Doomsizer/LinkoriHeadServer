from rest_framework import serializers

from .country_utils import detect_country_code

ALLOWED_SCHEMES = {"vless", "hysteria2", "hy2", "ss", "trojan", "vmess", "tuic", "wg"}


class OwnInboundResultSerializer(serializers.Serializer):
    inbound_id = serializers.IntegerField(min_value=1)
    is_alive = serializers.BooleanField()
    latency_ms = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class ProbeReportSerializer(serializers.Serializer):
    source = serializers.SlugField(max_length=64, required=False, default="")
    network_type = serializers.ChoiceField(
        choices=["lte", "wifi"],
        required=False,
        allow_null=True,
        default=None,
    )
    configs = serializers.ListField(
        child=serializers.JSONField(),
        allow_empty=True,
    )
    config_sources = serializers.DictField(
        child=serializers.CharField(max_length=128, allow_blank=True),
        required=False,
        default=dict,
    )
    own_results = OwnInboundResultSerializer(many=True, required=False, default=list)
    sync_own = serializers.BooleanField(required=False, default=True)

    def _validate_uri(self, raw_uri: str) -> str:
        uri = raw_uri.strip()
        if not uri or "://" not in uri:
            raise serializers.ValidationError(f"Некорректная ссылка конфига: {uri[:64]}")
        scheme = uri.split("://", 1)[0].lower()
        if scheme not in ALLOWED_SCHEMES:
            raise serializers.ValidationError(f"Неподдерживаемая схема протокола: {scheme}")
        return uri

    def validate(self, attrs):
        raw_configs = attrs.get("configs", [])
        source_map = attrs.get("config_sources") or {}

        normalized: list[dict] = []
        seen: set[str] = set()

        for item in raw_configs:
            if isinstance(item, str):
                raw_uri = item.strip()
                if not raw_uri:
                    continue
                uri = self._validate_uri(raw_uri)
                origin = str(source_map.get(uri) or source_map.get(raw_uri) or "").strip()[:128]
                latency = None
                country = ""
            elif isinstance(item, dict):
                raw_uri = str(item.get("uri") or "").strip()
                if not raw_uri:
                    continue
                uri = self._validate_uri(raw_uri)
                origin = str(
                    item.get("source")
                    or item.get("origin")
                    or item.get("origin_source")
                    or source_map.get(uri)
                    or ""
                ).strip()[:128]
                raw_lat = item.get("latency_ms")
                latency = int(raw_lat) if isinstance(raw_lat, (int, float)) and raw_lat >= 0 else None
                country = str(item.get("country_code") or item.get("country") or "").upper().strip()[:8]
            else:
                raise serializers.ValidationError("Элемент configs должен быть строкой или объектом.")

            if uri in seen:
                continue
            seen.add(uri)

            if not country:
                country = detect_country_code(uri)

            normalized.append(
                {
                    "uri": uri,
                    "origin_source": origin,
                    "latency_ms": latency,
                    "country_code": country,
                }
            )

        attrs["normalized_configs"] = normalized
        return attrs