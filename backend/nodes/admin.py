from django.contrib import admin, messages

from .models import NodeInbound, VpnNode
from .xui_sync import XuiSyncError, sync_node_inbounds


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
        "lte_health_status",
        "wifi_health_status",
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
        "probe_xray_uuid",
        "inbounds_count",
        "is_enabled",
        "priority",
        "updated_at",
    )
    list_filter = ("is_enabled", "country_code")
    search_fields = ("name", "country_code", "ip_address", "panel_url", "=probe_xray_uuid")
    ordering = ("priority", "name")
    inlines = (NodeInboundInline,)
    actions = ("sync_selected_nodes", "provision_active_subs_to_nodes")
    fieldsets = (
        (
            "Основное",
            {"fields": ("name", "country_code", "flag_emoji", "ip_address", "is_enabled", "priority")},
        ),
        (
            "Подключение к 3x-ui (API Token)",
            {
                "fields": (
                    "panel_url",
                    "panel_api_token",
                    "panel_verify_ssl",
                    "probe_xray_uuid",
                ),
            },
        ),
    )

    @admin.display(description="Инбаундов")
    def inbounds_count(self, obj):
        return obj.inbounds.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.is_enabled and obj.panel_api_token.strip():
            try:
                res = sync_node_inbounds(obj)
                from billing.tasks import provision_active_subscriptions_to_node

                provision_active_subscriptions_to_node.delay(obj.id)
                self.message_user(
                    request,
                    (
                        f"Инбаунды ноды «{obj.name}» синхронизированы: "
                        f"создано {res.created}, обновлено {res.updated}, "
                        f"отключено {res.disabled}, пропущено {res.skipped}. "
                        f"Админ-UUID: {res.probe_uuid or '-'}. "
                        f"Активные подписки поставлены в очередь на досинку."
                    ),
                    level=messages.SUCCESS,
                )
            except XuiSyncError as exc:
                self.message_user(
                    request,
                    f"Нода «{obj.name}» сохранена, но синхронизация 3x-ui не удалась: {exc}",
                    level=messages.WARNING,
                )

    @admin.action(description="Синхронизировать инбаунды из 3x-ui (и докинуть юзеров)")
    def sync_selected_nodes(self, request, queryset):
        from billing.tasks import provision_active_subscriptions_to_node

        for node in queryset:
            try:
                res = sync_node_inbounds(node)
                if node.is_enabled:
                    provision_active_subscriptions_to_node.delay(node.id)
                self.message_user(
                    request,
                    (
                        f"Нода «{node.name}»: создано {res.created}, "
                        f"обновлено {res.updated}, отключено {res.disabled}, "
                        f"пропущено {res.skipped}. Админ-UUID: {res.probe_uuid or '-'}. "
                        f"Досинка активных подписок запущена."
                    ),
                    level=messages.SUCCESS,
                )
            except XuiSyncError as exc:
                self.message_user(
                    request,
                    f"Ошибка синхронизации «{node.name}»: {exc}",
                    level=messages.ERROR,
                )

    @admin.action(description="Выдать доступ активным подпискам на выбранные ноды")
    def provision_active_subs_to_nodes(self, request, queryset):
        from billing.tasks import provision_active_subscriptions_to_node

        count = 0
        for node in queryset.filter(is_enabled=True):
            provision_active_subscriptions_to_node.delay(node.id)
            count += 1
        self.message_user(
            request,
            f"Запущена досинка активных подписок на {count} нод(ы).",
            level=messages.SUCCESS,
        )


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
        "lte_health_status",
        "lte_latency_ms",
        "wifi_health_status",
        "wifi_latency_ms",
        "last_checked_at",
    )
    list_filter = (
        "protocol",
        "health_status",
        "lte_health_status",
        "wifi_health_status",
        "is_enabled",
        "node__country_code",
    )
    search_fields = ("display_name", "connect_host", "node__name", "node__ip_address")
    raw_id_fields = ("node",)
    readonly_fields = ("last_checked_at",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.is_enabled and obj.node.is_enabled:
            from billing.tasks import provision_active_subscriptions_to_node

            provision_active_subscriptions_to_node.delay(obj.node_id)