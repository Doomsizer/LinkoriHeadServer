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
        "is_legal_accepted",
        "xray_uuid",
        "referral_code",
        "balance_kopeks",
        "is_active",
        "date_joined",
    )
    list_filter = ("is_legal_accepted", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("=telegram_id", "=xray_uuid", "telegram_username", "username", "referral_code")
    readonly_fields = ("date_joined", "last_login")
    raw_id_fields = ("referred_by",)

    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Telegram и биллинг",
            {
                "fields": (
                    "telegram_id",
                    "telegram_username",
                    "xray_uuid",
                    "referral_code",
                    "referred_by",
                    "balance_kopeks",
                    "is_legal_accepted",
                    "legal_accepted_at",
                )
            },
        ),
    )