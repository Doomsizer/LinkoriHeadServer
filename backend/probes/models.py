import hashlib

from django.db import models


def hash_uri(uri: str) -> str:
    return hashlib.sha256(uri.encode("utf-8")).hexdigest()


class ProbeSnapshot(models.Model):
    source = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        verbose_name="Источник (стенд)",
    )
    config_hash = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="SHA-256 набора",
    )
    configs = models.JSONField(default=list, verbose_name="Рабочие конфиги")
    added_configs = models.JSONField(default=list, blank=True, verbose_name="Добавлены")
    removed_configs = models.JSONField(default=list, blank=True, verbose_name="Удалены")
    is_changed = models.BooleanField(default=True, verbose_name="Набор изменился")
    total_count = models.PositiveIntegerField(default=0, verbose_name="Всего рабочих")
    confirmations_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Подтверждений без изменений",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Создан")
    last_confirmed_at = models.DateTimeField(auto_now=True, verbose_name="Последнее подтверждение")

    class Meta:
        verbose_name = "Снимок проверки"
        verbose_name_plural = "Снимки проверок"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.source} | {self.total_count} шт. | {self.created_at:%Y-%m-%d %H:%M}"


class WorkingPublicConfig(models.Model):
    source = models.CharField(
        max_length=64,
        default="default",
        db_index=True,
        verbose_name="Источник (стенд)",
    )
    uri = models.TextField(verbose_name="Ссылка конфига")
    uri_hash = models.CharField(max_length=64, db_index=True, verbose_name="SHA-256 ссылки")
    protocol = models.CharField(
        max_length=24,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Протокол",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Работает")
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="Впервые найден")
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name="Последнее подтверждение")

    class Meta:
        verbose_name = "Рабочий конфиг стенда"
        verbose_name_plural = "Рабочие конфиги стенда"
        ordering = ["-is_active", "-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "uri_hash"],
                name="uniq_probe_source_uri_hash",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.uri_hash:
            self.uri_hash = hash_uri(self.uri)
        if not self.protocol and "://" in self.uri:
            self.protocol = self.uri.split("://", 1)[0].lower()[:24]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        state = "OK" if self.is_active else "DEAD"
        return f"[{state}] {self.protocol} | {self.uri[:48]}"