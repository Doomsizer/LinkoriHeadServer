from django.contrib import admin

from .models import Payment, Plan, ReferralReward, Subscription, SubscriptionDevice
from .tasks import provision_subscription_to_panels


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
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
    search_fields = ("code", "name", "description")
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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        provision_subscription_to_panels.delay(str(obj.id))

    @admin.display(description="Устройств")
    def devices_count(self, obj):
        return obj.devices.count()

    @admin.action(description="Активировать выбранные подписки")
    def mark_active(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        queryset.update(status=Subscription.Status.ACTIVE)
        for sub_id in ids:
            provision_subscription_to_panels.delay(str(sub_id))

    @admin.action(description="Приостановить выбранные подписки")
    def mark_suspended(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        queryset.update(status=Subscription.Status.SUSPENDED)
        for sub_id in ids:
            provision_subscription_to_panels.delay(str(sub_id))

    @admin.action(description="Отозвать выбранные подписки")
    def mark_revoked(self, request, queryset):
        ids = list(queryset.values_list("id", flat=True))
        queryset.update(status=Subscription.Status.REVOKED)
        for sub_id in ids:
            provision_subscription_to_panels.delay(str(sub_id))


@admin.register(SubscriptionDevice)
class SubscriptionDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
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


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_id",
        "user",
        "plan",
        "method",
        "provider",
        "amount_kopeks",
        "status",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "method", "provider", "created_at")
    search_fields = ("=payment_id", "=external_id", "=user__telegram_id", "user__telegram_username")
    raw_id_fields = ("user", "subscription")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ("id", "referrer", "referred_user", "amount_kopeks", "created_at")
    list_filter = ("created_at",)
    search_fields = ("=referrer__telegram_id", "=referred_user__telegram_id")
    raw_id_fields = ("referrer", "referred_user", "payment")
    readonly_fields = ("created_at",)