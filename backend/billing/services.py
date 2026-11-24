from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts.email_utils import EmailValidationError, validate_email_domain
from accounts.models import User
from accounts.services import AccountLinkError, attach_or_merge_email

from .models import (
    Payment,
    Plan,
    ReferralReward,
    Subscription,
    generate_payment_id,
)
from .platega import (
    PlategaError,
    create_platega_transaction,
    fetch_platega_transaction_status,
)
from .tasks import provision_subscription_to_panels

GIGABYTE = 1024 ** 3
MAX_TRANSACTION_KOPEKS = 1_000_000  # 10 000 руб.
TRIAL_IP_LIMIT_WINDOW = 60 * 60 * 24 * 7  # 7 дней
TRIAL_IP_MAX_ATTEMPTS = 2


class BillingError(Exception):
    status_code = 400


class BillingNotFoundError(BillingError):
    status_code = 404


class LegalConsentRequiredError(BillingError):
    status_code = 403


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
        "is_trial": plan.is_trial,
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


def extend_subscription_by_timedelta(
    user: User,
    delta: timedelta,
    plan: Plan,
    reset_traffic_if_expired: bool = True,
    now=None,
) -> Subscription:
    now = now or timezone.now()
    traffic_limit_bytes = plan.traffic_limit_gb * GIGABYTE if plan.traffic_limit_gb > 0 else 0

    active_sub = (
        Subscription.objects.select_for_update()
        .filter(user=user, status=Subscription.Status.ACTIVE, expires_at__gt=now)
        .order_by("-expires_at")
        .first()
    )
    if active_sub is not None:
        if not plan.is_trial:
            active_sub.plan = plan
        active_sub.max_devices = max(active_sub.max_devices, plan.max_devices)
        if traffic_limit_bytes == 0:
            active_sub.traffic_limit_bytes = 0
        elif active_sub.traffic_limit_bytes > 0:
            active_sub.traffic_limit_bytes = max(
                active_sub.traffic_limit_bytes, traffic_limit_bytes
            )
        active_sub.expires_at = active_sub.expires_at + delta
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
        if reset_traffic_if_expired:
            expired_sub.traffic_used_bytes = 0
        expired_sub.traffic_limit_bytes = traffic_limit_bytes
        expired_sub.expires_at = now + delta
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
        expires_at=now + delta,
    )


def grant_or_extend_subscription(user: User, plan: Plan, now=None) -> Subscription:
    return extend_subscription_by_timedelta(
        user=user,
        delta=timedelta(days=plan.duration_days),
        plan=plan,
        now=now,
    )


def apply_referral_reward(payment: Payment) -> ReferralReward | None:
    if payment.plan.is_trial:
        return None
    if settings.REFERRAL_BONUS_PERCENT <= 0:
        return None

    user = payment.user
    if not user.referred_by_id or user.referred_by_id == user.id:
        return None
    if ReferralReward.objects.filter(referrer_id=user.referred_by_id, payment=payment).exists():
        return None

    bonus_hours = max(1, (payment.plan.duration_days * 24 * settings.REFERRAL_BONUS_PERCENT) // 100)
    referrer = User.objects.select_for_update().get(pk=user.referred_by_id)

    ref_existing_sub = (
        Subscription.objects.select_related("plan")
        .filter(user=referrer)
        .order_by("-expires_at")
        .first()
    )
    target_plan = ref_existing_sub.plan if ref_existing_sub else payment.plan
    ref_sub = extend_subscription_by_timedelta(
        user=referrer,
        delta=timedelta(hours=bonus_hours),
        plan=target_plan,
        reset_traffic_if_expired=False,
    )

    reward = ReferralReward.objects.create(
        referrer=referrer,
        referred_user=user,
        payment=payment,
        bonus_hours=bonus_hours,
        amount_kopeks=0,
    )

    ref_sub_id_str = str(ref_sub.id)
    transaction.on_commit(lambda: provision_subscription_to_panels.delay(ref_sub_id_str))
    return reward


def _resolve_platega_email(user: User, explicit_email: str = "") -> str:
    if user.email:
        return user.email
    if explicit_email:
        return explicit_email
    if user.telegram_id:
        return f"{user.telegram_id}@telegram.org"
    return f"user_{user.id}@linkori.org"


def _check_trial_eligibility(user: User, payment_channel: str, client_ip: str | None):
    if user.has_used_trial:
        raise BillingError("Пробный период доступен только один раз на аккаунт.")
    if get_active_subscription(user) is not None:
        raise BillingError("Пробный период недоступен при наличии активной подписки.")
    if payment_channel != "sbp":
        raise BillingError("Для пробного периода доступна только оплата через СБП.")
    if user.email:
        try:
            validate_email_domain(user.email, strict_for_trial=True)
        except EmailValidationError as exc:
            raise BillingError(str(exc)) from exc
    if client_ip:
        ip_key = f"trial_ip:{client_ip}"
        attempts = cache.get(ip_key, 0)
        if attempts >= TRIAL_IP_MAX_ATTEMPTS:
            raise BillingError("Превышен лимит активаций пробного периода с вашего IP.")
        cache.set(ip_key, attempts + 1, timeout=TRIAL_IP_LIMIT_WINDOW)


@transaction.atomic
def create_platega_or_stub_payment(
    user: User,
    plan_id: int,
    payment_channel: str = "sbp",
    email: str = "",
    client_ip: str | None = None,
) -> Payment:
    plan = Plan.objects.filter(id=plan_id, is_active=True).first()
    if plan is None:
        raise BillingNotFoundError("Тариф не найден")

    if plan.price_kopeks > MAX_TRANSACTION_KOPEKS:
        raise BillingError("Сумма одной транзакции не должна превышать 10 000 руб.")

    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_legal_accepted:
        raise LegalConsentRequiredError(
            "Перед покупкой необходимо принять Политику конфиденциальности и Пользовательское соглашение."
        )

    cleaned_email = ""
    if email:
        try:
            user = attach_or_merge_email(user, email)
            cleaned_email = user.email or ""
        except (EmailValidationError, AccountLinkError) as exc:
            raise BillingError(str(exc)) from exc

    if plan.is_trial:
        _check_trial_eligibility(user=user, payment_channel=payment_channel, client_ip=client_ip)

    pay_id = generate_payment_id("inv")
    provider = settings.PAYMENT_PROVIDER
    web_base = settings.SUB_WEB_URL.rstrip("/")

    if provider == "stub":
        if not settings.ALLOW_STUB_PAYMENTS:
            raise BillingError("Тестовая оплата отключена.")
        return Payment.objects.create(
            payment_id=pay_id,
            user=user,
            plan=plan,
            method=Payment.Method.EXTERNAL,
            payment_channel=payment_channel,
            provider="stub",
            amount_kopeks=plan.price_kopeks,
            status=Payment.Status.PENDING,
            payment_url=f"{web_base}/api/billing/mock-pay/{pay_id}/",
            metadata={"email": cleaned_email} if cleaned_email else {},
        )

    if provider != "platega":
        raise BillingError(f"Платежный провайдер '{provider}' не поддерживается.")

    platega_email = _resolve_platega_email(user=user, explicit_email=cleaned_email)
    try:
        tx = create_platega_transaction(
            payment_id=pay_id,
            amount_kopeks=plan.price_kopeks,
            payment_method_key=payment_channel,
            description=f"Linkori: {plan.name}",
            user_email=platega_email,
            user_id_str=str(user.telegram_id or user.id),
            user_name=user.telegram_username or user.email or f"user_{user.id}",
            return_url=f"{web_base}/cabinet?payment={pay_id}&status=success",
            failed_url=f"{web_base}/cabinet?payment={pay_id}&status=failed",
        )
    except PlategaError as exc:
        raise BillingError(str(exc)) from exc

    return Payment.objects.create(
        payment_id=pay_id,
        user=user,
        plan=plan,
        method=Payment.Method.EXTERNAL,
        payment_channel=payment_channel,
        provider="platega",
        external_id=tx["transaction_id"],
        amount_kopeks=plan.price_kopeks,
        status=Payment.Status.PENDING,
        payment_url=tx["redirect_url"],
        metadata={"email": platega_email, "channel": payment_channel},
    )


def sync_payment_status_with_provider(payment: Payment) -> Payment:
    if payment.status != Payment.Status.PENDING:
        return payment

    now = timezone.now()
    ttl_delta = timedelta(minutes=settings.PAYMENT_PENDING_TTL_MINUTES)

    if payment.provider == "platega" and payment.external_id:
        try:
            remote_status = fetch_platega_transaction_status(payment.external_id)
        except PlategaError:
            remote_status = ""

        if remote_status == "CONFIRMED":
            return finalize_paid_payment(payment.payment_id)
        if remote_status in ("CANCELED", "CHARGEBACKED"):
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            return payment

    if payment.created_at <= now - ttl_delta:
        payment.status = Payment.Status.EXPIRED
        payment.save(update_fields=["status", "updated_at"])

    return payment


@transaction.atomic
def finalize_paid_payment(payment_id: str) -> Payment:
    payment = (
        Payment.objects.select_for_update(of=("self",))
        .select_related("user", "plan")
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
    user = User.objects.select_for_update().get(pk=payment.user_id)

    sub = grant_or_extend_subscription(user=user, plan=payment.plan, now=now)
    if payment.plan.is_trial and not user.has_used_trial:
        user.has_used_trial = True
        user.save(update_fields=["has_used_trial"])

    payment.status = Payment.Status.PAID
    payment.subscription = sub
    if payment.paid_at is None:
        payment.paid_at = now
    payment.save(update_fields=["status", "subscription", "paid_at", "updated_at"])

    apply_referral_reward(payment)

    sub_id_str = str(sub.id)
    transaction.on_commit(lambda: provision_subscription_to_panels.delay(sub_id_str))
    return payment