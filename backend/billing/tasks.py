import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from nodes.xui_sync import sync_user_subscription_on_all_panels

from .models import Payment, Subscription

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def provision_subscription_to_panels(subscription_id: str):
    sub = Subscription.objects.select_related("user").filter(id=subscription_id).first()
    if sub is None:
        return

    expires_ms = int(sub.expires_at.timestamp() * 1000)
    result = sync_user_subscription_on_all_panels(
        user=sub.user,
        expires_at_ms=expires_ms,
        enable=sub.is_valid_now(),
        total_gb_bytes=sub.traffic_limit_bytes,
    )
    if result["errors"]:
        logger.warning("Ошибки провижининга подписки %s: %s", subscription_id, result["errors"])


@shared_task(ignore_result=True)
def expire_overdue_subscriptions():
    now = timezone.now()
    overdue = list(
        Subscription.objects.select_related("user")
        .filter(status=Subscription.Status.ACTIVE, expires_at__lte=now)
    )
    if not overdue:
        return

    user_ids = {sub.user_id for sub in overdue}
    Subscription.objects.filter(id__in=[sub.id for sub in overdue]).update(
        status=Subscription.Status.EXPIRED
    )

    for user_id in user_ids:
        still_active = Subscription.objects.filter(
            user_id=user_id,
            status=Subscription.Status.ACTIVE,
            expires_at__gt=now,
        ).exists()
        if still_active:
            continue

        sample_sub = next(sub for sub in overdue if sub.user_id == user_id)
        expires_ms = int(sample_sub.expires_at.timestamp() * 1000)
        sync_user_subscription_on_all_panels(
            user=sample_sub.user,
            expires_at_ms=expires_ms,
            enable=False,
            total_gb_bytes=sample_sub.traffic_limit_bytes,
        )


@shared_task(ignore_result=True)
def expire_stale_pending_payments():
    from .services import sync_payment_status_with_provider

    cutoff = timezone.now() - timedelta(minutes=settings.PAYMENT_PENDING_TTL_MINUTES)
    stale_payments = Payment.objects.filter(
        status=Payment.Status.PENDING,
        created_at__lte=cutoff,
    ).order_by("created_at")[:100]

    for payment in stale_payments:
        try:
            sync_payment_status_with_provider(payment)
        except Exception as exc:
            logger.warning("Не удалось закрыть истекший платеж %s: %s", payment.payment_id, exc)