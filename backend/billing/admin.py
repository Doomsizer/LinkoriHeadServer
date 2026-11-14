from django.contrib import admin

from .models import Plan, Subscription, SubscriptionDevice


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "duration_days",
        "price_kopeks",
        "traffic_limit_gb",
        "max_devices",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active", "duration_days")
    search_fields = ("code", "name")
    ordering = ("sort_order", "price_kopeks")


class SubscriptionDeviceInline(admin.TabularInline):
    model = SubscriptionDevice
    extra = 0
    fields = (
        "hwid",
        "device_os",
        "ver_os",
        "device_model",
        "last_ip",
        "is_blocked",
        "last_seen_at",
    )
    readonly_fields = ("first_seen_at", "last_seen_at")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan",
        "status",
        "sub_token",
        "max_devices",
        "devices_count",
        "expires_at",
        "created_at",
    )
    list_filter = ("status", "plan", "expires_at", "created_at")
    search_fields = (
        "=sub_token",
        "=xray_uuid",
        "=user__telegram_id",
        "user__telegram_username",
        "devices__hwid",
    )
    raw_id_fields = ("user",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (SubscriptionDeviceInline,)
    actions = ("mark_active", "mark_suspended", "mark_revoked")

    @admin.display(description="Устройств")
    def devices_count(self, obj):
        return obj.devices.count()

    @admin.action(description="Активировать выбранные подписки")
    def mark_active(self, request, queryset):
        queryset.update(status=Subscription.Status.ACTIVE)

    @admin.action(description="Приостановить выбранные подписки")
    def mark_suspended(self, request, queryset):
        queryset.update(status=Subscription.Status.SUSPENDED)

    @admin.action(description="Отозвать выбранные подписки")
    def mark_revoked(self, request, queryset):
        queryset.update(status=Subscription.Status.REVOKED)


@admin.register(SubscriptionDevice)
class SubscriptionDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "hwid",
        "subscription",
        "device_os",
        "ver_os",
        "device_model",
        "last_ip",
        "is_blocked",
        "last_seen_at",
    )
    list_filter = ("is_blocked", "device_os", "last_seen_at")
    search_fields = (
        "hwid",
        "=subscription__sub_token",
        "=subscription__user__telegram_id",
        "subscription__user__telegram_username",
        "last_ip",
        "device_model",
    )
    raw_id_fields = ("subscription",)
    readonly_fields = ("first_seen_at", "last_seen_at")
    actions = ("block_devices", "unblock_devices")

    @admin.action(description="Заблокировать выбранные устройства")
    def block_devices(self, request, queryset):
        queryset.update(is_blocked=True)

    @admin.action(description="Разблокировать выбранные устройства")
    def unblock_devices(self, request, queryset):
        queryset.update(is_blocked=False)
