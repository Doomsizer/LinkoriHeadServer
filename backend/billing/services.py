from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User

from .models import (
    Payment,
    Plan,
    ReferralReward,
    Subscription,
    generate_payment_id,
)
from .tasks import provision_subscription_to_panels

GIGABYTE = 1024 ** 3
MAX_TRANSACTION_KOPEKS = 1_000_000  # 10 000 руб.


class BillingError(Exception):
    status_code = 400


class BillingNotFoundError(BillingError):
    status_code = 404


class InsufficientBalanceError(BillingError):
    status_code = 400


def format_iso_utc(dt) -> str:
    if dt is None:
        return ""
    return dt.isoformat().replace("+00:00", "Z")


def serialize_plan(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "duration_days": plan.duration_days,
        "price_kopeks": plan.price_kopeks,
        "max_devices": plan.max_devices,
        "traffic_limit_gb": plan.traffic_limit_gb if plan.traffic_limit_gb > 0 else None,
    }


def serialize_subscription(sub: Subscription) -> dict:
    return {
        "id": str(sub.id),
        "sub_token": sub.sub_token,
        "status": sub.status,
        "plan_name": sub.plan.name,
        "max_devices": sub.max_devices,
        "traffic_used_bytes": sub.traffic_used_bytes,
        "traffic_limit_bytes": sub.traffic_limit_bytes if sub.traffic_limit_bytes > 0 else None,
        "expires_at": format_iso_utc(sub.expires_at),
    }


def get_active_subscription(user: User, now=None) -> Subscription | None:
    now = now or timezone.now()
    return (
        Subscription.objects.select_related("plan")
        .filter(
            user=user,
            status=Subscription.Status.ACTIVE,
            expires_at__gt=now,
        )
        .order_by("-expires_at")
        .first()
    )


def grant_or_extend_subscription(user: User, plan: Plan, now=None) -> Subscription:
    now = now or timezone.now()
    traffic_limit_bytes = plan.traffic_limit_gb * GIGABYTE if plan.traffic_limit_gb > 0 else 0
    duration = timedelta(days=plan.duration_days)

    active_sub = (
        Subscription.objects.select_for_update()
        .filter(user=user, status=Subscription.Status.ACTIVE, expires_at__gt=now)
        .order_by("-expires_at")
        .first()
    )
    if active_sub is not None:
        active_sub.plan = plan
        active_sub.max_devices = plan.max_devices
        active_sub.traffic_limit_bytes = traffic_limit_bytes
        active_sub.expires_at = active_sub.expires_at + duration
        active_sub.save(
            update_fields=["plan", "max_devices", "traffic_limit_bytes", "expires_at", "updated_at"]
        )
        return active_sub

    expired_sub = (
        Subscription.objects.select_for_update()
        .filter(
            user=user,
            status__in=[Subscription.Status.ACTIVE, Subscription.Status.EXPIRED],
        )
        .order_by("-expires_at")
        .first()
    )
    if expired_sub is not None:
        expired_sub.plan = plan
        expired_sub.status = Subscription.Status.ACTIVE
        expired_sub.max_devices = plan.max_devices
        expired_sub.traffic_used_bytes = 0
        expired_sub.traffic_limit_bytes = traffic_limit_bytes
        expired_sub.expires_at = now + duration
        expired_sub.save(
            update_fields=[
                "plan",
                "status",
                "max_devices",
                "traffic_used_bytes",
                "traffic_limit_bytes",
                "expires_at",
                "updated_at",
            ]
        )
        return expired_sub

    return Subscription.objects.create(
        user=user,
        plan=plan,
        xray_uuid=user.xray_uuid,
        status=Subscription.Status.ACTIVE,
        max_devices=plan.max_devices,
        traffic_used_bytes=0,
        traffic_limit_bytes=traffic_limit_bytes,
        expires_at=now + duration,
    )


def apply_referral_reward(payment: Payment) -> ReferralReward | None:
    if settings.REFERRAL_BONUS_PERCENT <= 0:
        return None
    user = payment.user
    if not user.referred_by_id or user.referred_by_id == user.id:
        return None
    if ReferralReward.objects.filter(payment=payment).exists():
        return None

    bonus_kopeks = (payment.amount_kopeks * settings.REFERRAL_BONUS_PERCENT) // 100
    if bonus_kopeks <= 0:
        return None

    referrer = User.objects.select_for_update().get(pk=user.referred_by_id)
    referrer.balance_kopeks += bonus_kopeks
    referrer.save(update_fields=["balance_kopeks"])

    return ReferralReward.objects.create(
        referrer=referrer,
        referred_user=user,
        payment=payment,
        amount_kopeks=bonus_kopeks,
    )


@transaction.atomic
def pay_with_balance(telegram_id: int, plan_id: int) -> tuple[Payment, Subscription]:
    plan = Plan.objects.filter(id=plan_id, is_active=True).first()
    if plan is None:
        raise BillingNotFoundError("Тариф не найден")

    if plan.price_kopeks > MAX_TRANSACTION_KOPEKS:
        raise BillingError("Сумма одной транзакции не должна превышать 10 000 руб.")

    user = User.objects.select_for_update().filter(telegram_id=telegram_id).first()
    if user is None:
        raise BillingNotFoundError("Пользователь не найден")

    if user.balance_kopeks < plan.price_kopeks:
        raise InsufficientBalanceError("Недостаточно средств на балансе")

    now = timezone.now()
    user.balance_kopeks -= plan.price_kopeks
    user.save(update_fields=["balance_kopeks"])

    sub = grant_or_extend_subscription(user=user, plan=plan, now=now)
    payment = Payment.objects.create(
        payment_id=generate_payment_id("bal"),
        user=user,
        plan=plan,
        method=Payment.Method.BALANCE,
        provider="balance",
        amount_kopeks=plan.price_kopeks,
        status=Payment.Status.PAID,
        subscription=sub,
        paid_at=now,
    )
    apply_referral_reward(payment)

    sub_id_str = str(sub.id)
    transaction.on_commit(lambda: provision_subscription_to_panels.delay(sub_id_str))
    return payment, sub


@transaction.atomic
def create_external_payment(telegram_id: int, plan_id: int, email: str = "") -> Payment:
    plan = Plan.objects.filter(id=plan_id, is_active=True).first()
    if plan is None:
        raise BillingNotFoundError("Тариф не найден")

    if plan.price_kopeks > MAX_TRANSACTION_KOPEKS:
        raise BillingError("Сумма одной транзакции не должна превышать 10 000 руб.")

    user = User.objects.filter(telegram_id=telegram_id).first()
    if user is None:
        raise BillingNotFoundError("Пользователь не найден")

    pay_id = generate_payment_id("inv")
    provider = settings.PAYMENT_PROVIDER

    if provider == "stub":
        base_web = settings.SUB_WEB_URL.rstrip("/")
        payment_url = f"{base_web}/api/billing/mock-pay/{pay_id}/"
    else:
        raise BillingError(f"Платежный провайдер '{provider}' еще не настроен")

    metadata = {"email": email} if email else {}
    return Payment.objects.create(
        payment_id=pay_id,
        user=user,
        plan=plan,
        method=Payment.Method.EXTERNAL,
        provider=provider,
        amount_kopeks=plan.price_kopeks,
        status=Payment.Status.PENDING,
        payment_url=payment_url,
        metadata=metadata,
    )


@transaction.atomic
def finalize_paid_payment(payment_id: str) -> Payment:
    payment = (
        Payment.objects.select_for_update()
        .select_related("user", "plan", "subscription")
        .filter(payment_id=payment_id)
        .first()
    )
    if payment is None:
        raise BillingNotFoundError("Платеж не найден")

    if payment.status == Payment.Status.PAID and payment.subscription_id is not None:
        return payment

    if payment.status == Payment.Status.FAILED:
        raise BillingError("Платеж уже отклонен")

    now = timezone.now()
    sub = grant_or_extend_subscription(user=payment.user, plan=payment.plan, now=now)
    payment.status = Payment.Status.PAID
    payment.subscription = sub
    if payment.paid_at is None:
        payment.paid_at = now
    payment.save(update_fields=["status", "subscription", "paid_at", "updated_at"])

    apply_referral_reward(payment)

    sub_id_str = str(sub.id)
    transaction.on_commit(lambda: provision_subscription_to_panels.delay(sub_id_str))
    return payment