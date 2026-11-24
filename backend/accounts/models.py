import secrets
import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models

from .email_utils import canonicalize_email, normalize_email_raw


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
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Email",
    )
    canonical_email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Канонический Email",
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
        verbose_name="Баланс (копейки, не используется)",
    )
    has_used_trial = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Использовал триал",
    )
    is_legal_accepted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Приняты документы и cookies",
    )
    legal_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата принятия документов",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        if self.email is not None:
            norm = normalize_email_raw(self.email)
            self.email = norm if norm else None
        if self.email:
            self.canonical_email = canonicalize_email(self.email)
        else:
            self.canonical_email = None

        if not self.username:
            if self.telegram_id is not None:
                self.username = f"tg_{self.telegram_id}"
            elif self.email:
                self.username = f"em_{secrets.token_hex(6)}"

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
        if self.telegram_username and self.telegram_username != str(self.telegram_id):
            return f"@{self.telegram_username} ({self.telegram_id})"
        if self.telegram_id:
            return f"tg:{self.telegram_id}"
        if self.email:
            return self.email
        return self.username