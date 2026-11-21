from rest_framework import serializers

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
        child=serializers.CharField(max_length=4096, trim_whitespace=True),
        allow_empty=True,
    )
    own_results = OwnInboundResultSerializer(many=True, required=False, default=list)
    sync_own = serializers.BooleanField(required=False, default=False)

    def validate_configs(self, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_uri in value:
            uri = raw_uri.strip()
            if not uri:
                continue
            if "://" not in uri:
                raise serializers.ValidationError(f"Некорректная ссылка конфига: {uri[:64]}")
            scheme = uri.split("://", 1)[0].lower()
            if scheme not in ALLOWED_SCHEMES:
                raise serializers.ValidationError(f"Неподдерживаемая схема протокола: {scheme}")
            if uri not in seen:
                seen.add(uri)
                cleaned.append(uri)
        return cleaned