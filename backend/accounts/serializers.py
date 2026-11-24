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
    is_legal_accepted = serializers.BooleanField(required=False, default=False)
    sync_panels = serializers.BooleanField(required=False, default=False)


class BotAcceptLegalSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField(min_value=1)
    accepted = serializers.BooleanField(required=False, default=True)


class TelegramAuthInitSerializer(serializers.Serializer):
    accepted_legal = serializers.BooleanField(required=False, default=False)
    referred_by_code = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )


class TelegramAuthConfirmSerializer(serializers.Serializer):
    auth_token = serializers.CharField(max_length=128)
    telegram_id = serializers.IntegerField(min_value=1)
    telegram_username = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )


class EmailOtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailOtpVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=10)
    accepted_legal = serializers.BooleanField(required=False, default=False)
    referred_by_code = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )


class WebApplyReferralSerializer(serializers.Serializer):
    referral_code = serializers.CharField(max_length=32)