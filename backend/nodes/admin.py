from django.contrib import admin

from .models import NodeInbound, VpnNode


class NodeInboundInline(admin.TabularInline):
    model = NodeInbound
    extra = 0
    fields = (
        "xui_inbound_id",
        "protocol",
        "display_name",
        "connect_host",
        "connect_port",
        "is_enabled",
        "health_status",
        "last_latency_ms",
    )
    readonly_fields = ("last_latency_ms", "last_checked_at")


@admin.register(VpnNode)
class VpnNodeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country_code",
        "flag_emoji",
        "ip_address",
        "auth_type",
        "is_enabled",
        "priority",
        "updated_at",
    )
    list_filter = ("is_enabled", "country_code")
    search_fields = ("name", "country_code", "ip_address", "panel_url")
    ordering = ("priority", "name")
    inlines = (NodeInboundInline,)
    fieldsets = (
        (
            "Основное",
            {"fields": ("name", "country_code", "flag_emoji", "ip_address", "is_enabled", "priority")},
        ),
        (
            "Подключение к 3x-ui",
            {
                "fields": ("panel_url", "panel_api_token", "panel_username", "panel_password"),
            },
        ),
    )

    @admin.display(description="Авторизация")
    def auth_type(self, obj):
        if obj.panel_api_token:
            return "API Token"
        if obj.panel_username:
            return "Login/Pass"
        return "Не задана"


@admin.register(NodeInbound)
class NodeInboundAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "node",
        "protocol",
        "connect_host",
        "connect_port",
        "is_enabled",
        "health_status",
        "last_latency_ms",
        "last_checked_at",
    )
    list_filter = ("protocol", "health_status", "is_enabled", "node__country_code")
    search_fields = ("display_name", "connect_host", "node__name", "node__ip_address")
    raw_id_fields = ("node",)
    readonly_fields = ("last_checked_at",)