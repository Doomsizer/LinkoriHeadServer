import secrets
import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


def generate_referral_code() -> str:
    return secrets.token_hex(5).upper()


class User(AbstractUser):
    telegram_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Telegram ID",
    )
    telegram_username = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Telegram username",
    )
    xray_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name="Единый Xray UUID",
    )
    referral_code = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        verbose_name="Реферальный код",
    )
    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
        verbose_name="Пригласивший пользователь",
    )
    balance_kopeks = models.BigIntegerField(
        default=0,
        verbose_name="Баланс (копейки)",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        if not self.username and self.telegram_id is not None:
            self.username = f"tg_{self.telegram_id}"
        if not self.referral_code:
            code = generate_referral_code()
            while User.objects.filter(referral_code=code).exists():
                code = generate_referral_code()
            self.referral_code = code
        super().save(*args, **kwargs)

    @property
    def balance_rub(self) -> Decimal:
        return Decimal(self.balance_kopeks) / Decimal(100)

    def __str__(self) -> str:
        if self.telegram_username:
            return f"@{self.telegram_username} ({self.telegram_id})"
        if self.telegram_id:
            return f"tg:{self.telegram_id}"
        return self.username