from django.db import models


class VpnNode(models.Model):
    name = models.CharField(max_length=128, unique=True, verbose_name="Название ноды")
    country_code = models.CharField(max_length=8, db_index=True, verbose_name="Код страны")
    flag_emoji = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Флаг (emoji)",
    )
    ip_address = models.GenericIPAddressField(verbose_name="IP-адрес")
    panel_url = models.URLField(max_length=255, verbose_name="URL панели 3x-ui")
    panel_username = models.CharField(max_length=128, verbose_name="Логин панели")
    panel_password = models.CharField(max_length=255, verbose_name="Пароль панели")
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Включена",
    )
    priority = models.IntegerField(
        default=100,
        db_index=True,
        verbose_name="Приоритет (меньше = выше)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")

    class Meta:
        verbose_name = "VPN-нода"
        verbose_name_plural = "VPN-ноды"
        ordering = ["priority", "name"]

    def __str__(self) -> str:
        prefix = f"{self.flag_emoji} " if self.flag_emoji else ""
        return f"{prefix}{self.name} ({self.country_code})"


class NodeInbound(models.Model):
    class Protocol(models.TextChoices):
        VLESS_REALITY = "vless_reality", "VLESS Reality"
        VLESS_WS = "vless_ws", "VLESS WS (Cloudflare)"
        HYSTERIA2 = "hysteria2", "Hysteria 2"
        SS = "ss", "Shadowsocks 2022"

    class HealthStatus(models.TextChoices):
        ONLINE = "online", "Online"
        DEGRADED = "degraded", "Degraded"
        OFFLINE = "offline", "Offline"
        UNKNOWN = "unknown", "Unknown"

    node = models.ForeignKey(
        VpnNode,
        on_delete=models.CASCADE,
        related_name="inbounds",
        verbose_name="Нода",
    )
    xui_inbound_id = models.PositiveIntegerField(verbose_name="ID инбаунда в 3x-ui")
    protocol = models.CharField(
        max_length=24,
        choices=Protocol.choices,
        db_index=True,
        verbose_name="Протокол",
    )
    display_name = models.CharField(
        max_length=128,
        verbose_name="Отображаемое имя в клиенте",
    )
    connect_host = models.CharField(
        max_length=255,
        verbose_name="Хост подключения (IP или домен)",
    )
    connect_port = models.PositiveIntegerField(verbose_name="Порт подключения")
    extra_params = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Дополнительные параметры (JSONB)",
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Включен",
    )
    health_status = models.CharField(
        max_length=16,
        choices=HealthStatus.choices,
        default=HealthStatus.UNKNOWN,
        db_index=True,
        verbose_name="Состояние",
    )
    last_latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Задержка (мс)",
    )
    last_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя проверка",
    )

    class Meta:
        verbose_name = "Инбаунд ноды"
        verbose_name_plural = "Инбаунды нод"
        ordering = ["node__priority", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["node", "xui_inbound_id"],
                name="uniq_node_xui_inbound",
            )
        ]

    def __str__(self) -> str:
        return f"{self.node.name} | {self.protocol} | {self.connect_host}:{self.connect_port}"
