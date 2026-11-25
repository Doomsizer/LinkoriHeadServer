import logging

import httpx
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def check_nodes_health():
    """Заглушка периодической задачи проверки доступности инбаундов."""
    logger.debug("Запуск задачи check_nodes_health")


@shared_task(ignore_result=True)
def send_probe_status_alert(
    network_label: str,
    failed_items: list[str],
    recovered_items: list[str],
):
    bot_token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    raw_admin_ids = (getattr(settings, "ADMIN_TELEGRAM_ID", "") or "").strip()
    if not bot_token or not raw_admin_ids:
        logger.debug("Уведомления в Telegram не настроены (нет TELEGRAM_BOT_TOKEN или ADMIN_TELEGRAM_ID)")
        return

    parts: list[str] = []
    if failed_items:
        lines = "\n".join(f"• {item}" for item in failed_items)
        parts.append(
            f"⚠️ Инбаунд не прошел проверку (сеть: {network_label}):\n{lines}"
        )
    if recovered_items:
        lines = "\n".join(f"• {item}" for item in recovered_items)
        parts.append(
            f"✅ Инбаунды восстановлены (сеть: {network_label}):\n{lines}"
        )

    if not parts:
        return

    text = "\n\n".join(parts)
    admin_ids = [x.strip() for x in raw_admin_ids.split(",") if x.strip()]
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    with httpx.Client(timeout=10.0) as client:
        for chat_id in admin_ids:
            try:
                resp = client.post(
                    api_url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Не удалось отправить алерт в Telegram %s: %s", chat_id, exc)