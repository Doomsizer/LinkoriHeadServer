from django.core.exceptions import ValidationError
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
    panel_url = models.URLField(
        max_length=255,
        verbose_name="URL панели 3x-ui (включая web_base_path)",
    )
    panel_api_token = models.CharField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="API-токен панели 3x-ui",
        help_text="Создается в 3x-ui: Settings -> Security -> API Token (Bearer)",
    )
    panel_username = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Логин панели (legacy)",
    )
    panel_password = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Пароль панели (legacy)",
    )
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

    def clean(self):
        super().clean()
        has_token = bool(self.panel_api_token.strip())
        has_legacy_creds = bool(self.panel_username.strip() and self.panel_password.strip())
        if not has_token and not has_legacy_creds:
            raise ValidationError(
                "Укажите API-токен панели 3x-ui (рекомендуется) или логин и пароль."
            )

    def __str__(self) -> str:
        prefix = f"{self.flag_emoji} " if self.flag_emoji else ""
        return f"{prefix}{self.name} ({self.country_code})"