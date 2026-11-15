from rest_framework import serializers


class BotGetOrCreateUserSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(min_value=1)
    telegram_username = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )
    referred_by_code = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )
    sync_panels = serializers.BooleanField(required=False, default=True)