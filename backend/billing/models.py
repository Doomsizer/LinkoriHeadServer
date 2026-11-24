import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_sub_token() -> str:
    return secrets.token_urlsafe(24)


def generate_ss2022_password() -> str:
    # Заглушка для исторической миграции billing/migrations/0001_initial.py
    return ""


def generate_payment_id(prefix: str = "inv") -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class Plan(models.Model):
    code = models.SlugField(max_length=64, unique=True, verbose_name="Код тарифа")
    name = models.CharField(max_length=128, verbose_name="Название")
    description = models.TextField(blank=True, default="", verbose_name="Описание")
    duration_days = models.PositiveIntegerField(verbose_name="Срок (дней)")
    price_kopeks = models.PositiveBigIntegerField(verbose_name="Цена (копейки)")
    traffic_limit_gb = models.PositiveIntegerField(
        default=0,
        verbose_name="Лимит трафика (ГБ, 0 = безлимит)",
    )
    max_devices = models.PositiveSmallIntegerField(
        default=10,
        verbose_name="Максимум устройств",
    )
    is_trial = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Пробный период (1 раз, только СБП, без реф-бонуса)",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активен")
    sort_order = models.PositiveIntegerField(default=100, verbose_name="Порядок сортировки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        ordering = ["sort_order", "price_kopeks"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        EXPIRED = "expired", "Истекла"
        SUSPENDED = "suspended", "Приостановлена"
        REVOKED = "revoked", "Отозвана"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="ID подписки",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name="Пользователь",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name="Тариф",
    )
    sub_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_sub_token,
        verbose_name="Токен подписки",
    )
    xray_uuid = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Xray UUID",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )
    max_devices = models.PositiveSmallIntegerField(
        default=10,
        verbose_name="Лимит устройств",
    )
    traffic_used_bytes = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Использовано трафика (байт)",
    )
    traffic_limit_bytes = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Лимит трафика (байт, 0 = безлимит)",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="Действует до",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.xray_uuid:
            if self.user_id and getattr(self.user, "xray_uuid", None):
                self.xray_uuid = self.user.xray_uuid
            else:
                self.xray_uuid = uuid.uuid4()
        super().save(*args, **kwargs)

    def is_valid_now(self, now=None) -> bool:
        now = now or timezone.now()
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at <= now:
            return False
        if self.traffic_limit_bytes > 0 and self.traffic_used_bytes >= self.traffic_limit_bytes:
            return False
        return True

    def __str__(self) -> str:
        return f"{self.user} | {self.plan.code} | {self.status}"


class SubscriptionDevice(models.Model):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="devices",
        verbose_name="Подписка",
    )
    hwid = models.CharField(
        max_length=128,
        db_index=True,
        verbose_name="HWID",
    )
    device_os = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="ОС устройства",
    )
    ver_os = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Версия ОС",
    )
    device_model = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Модель устройства",
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="User-Agent",
    )
    last_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Последний IP",
    )
    is_blocked = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Заблокировано",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="Первый запрос")
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name="Последний запрос")

    class Meta:
        verbose_name = "Устройство подписки"
        verbose_name_plural = "Устройства подписок"
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "hwid"],
                name="uniq_subscription_hwid",
            )
        ]

    def __str__(self) -> str:
        label = self.device_model or self.device_os or "Device"
        return f"{label} [{self.hwid}]"


class Payment(models.Model):
    class Method(models.TextChoices):
        BALANCE = "balance", "Баланс (устаревшее)"
        EXTERNAL = "external", "Внешний платеж"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PAID = "paid", "Оплачен"
        FAILED = "failed", "Ошибка / Отменен"

    payment_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="ID платежа",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Пользователь",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Тариф",
    )
    method = models.CharField(
        max_length=16,
        choices=Method.choices,
        default=Method.EXTERNAL,
        verbose_name="Способ оплаты",
    )
    payment_channel = models.CharField(
        max_length=16,
        blank=True,
        default="sbp",
        verbose_name="Метод шлюза (sbp/crypto)",
    )
    provider = models.CharField(
        max_length=32,
        default="platega",
        verbose_name="Провайдер",
    )
    external_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        verbose_name="ID транзакции в Platega",
    )
    amount_kopeks = models.PositiveBigIntegerField(verbose_name="Сумма (копейки)")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="Статус",
    )
    payment_url = models.URLField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="Ссылка на оплату",
    )
    subscription = models.ForeignKey(
        Subscription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        verbose_name="Выданная подписка",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Метаданные")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Оплачен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.payment_id} | {self.user} | {self.status}"


class ReferralReward(models.Model):
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_rewards",
        verbose_name="Пригласивший",
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_referral_rewards",
        verbose_name="Реферал",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="referral_rewards",
        verbose_name="Платеж",
    )
    bonus_hours = models.PositiveIntegerField(default=0, verbose_name="Бонус (часов к подписке)")
    amount_kopeks = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Сумма (копейки, устаревшее)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Реферальный бонус"
        verbose_name_plural = "Реферальные бонусы"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["referrer", "payment"],
                name="uniq_referral_reward_per_payment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.referrer} +{self.bonus_hours} ч. от {self.referred_user}"