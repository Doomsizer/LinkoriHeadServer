from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "telegram_id",
        "telegram_username",
        "email",
        "has_used_trial",
        "is_legal_accepted",
        "referral_code",
        "is_active",
        "date_joined",
    )
    list_filter = ("has_used_trial", "is_legal_accepted", "is_active", "is_staff", "date_joined")
    search_fields = (
        "=telegram_id",
        "=xray_uuid",
        "telegram_username",
        "email",
        "canonical_email",
        "username",
        "referral_code",
    )
    readonly_fields = ("date_joined", "last_login")
    raw_id_fields = ("referred_by",)

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Telegram, Email и подписки",
            {
                "fields": (
                    "telegram_id",
                    "telegram_username",
                    "canonical_email",
                    "xray_uuid",
                    "referral_code",
                    "referred_by",
                    "has_used_trial",
                    "is_legal_accepted",
                    "legal_accepted_at",
                )
            },
        ),
    )