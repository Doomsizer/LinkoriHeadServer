from django.contrib import admin

from .models import ProbeSnapshot, ProbeStand, WorkingPublicConfig


@admin.register(ProbeStand)
class ProbeStandAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "network_type",
        "short_token",
        "is_active",
        "last_seen_at",
        "created_at",
    )
    list_filter = ("network_type", "is_active", "created_at")
    search_fields = ("name", "token")
    readonly_fields = ("last_seen_at", "created_at")

    @admin.display(description="Токен")
    def short_token(self, obj):
        if len(obj.token) > 16:
            return f"{obj.token[:8]}...{obj.token[-6:]}"
        return obj.token


@admin.register(ProbeSnapshot)
class ProbeSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "total_count",
        "is_changed",
        "confirmations_count",
        "created_at",
        "last_confirmed_at",
    )
    list_filter = ("source", "is_changed", "created_at")
    search_fields = ("source", "config_hash")
    readonly_fields = (
        "config_hash",
        "configs",
        "added_configs",
        "removed_configs",
        "created_at",
        "last_confirmed_at",
    )


@admin.register(WorkingPublicConfig)
class WorkingPublicConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "country_code",
        "protocol",
        "origin_source",
        "latency_ms",
        "is_active",
        "short_uri",
        "last_seen_at",
    )
    list_filter = ("source", "is_active", "country_code", "protocol", "origin_source")
    search_fields = ("uri", "uri_hash", "source", "origin_source", "country_code")
    readonly_fields = ("uri_hash", "first_seen_at", "last_seen_at")

    @admin.display(description="URI")
    def short_uri(self, obj):
        return f"{obj.uri[:64]}..." if len(obj.uri) > 64 else obj.uri