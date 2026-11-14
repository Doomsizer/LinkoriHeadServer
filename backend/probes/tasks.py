import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def check_nodes_health():
    """Заглушка периодической задачи проверки доступности инбаундов."""
    logger.debug("Запуск задачи check_nodes_health")
