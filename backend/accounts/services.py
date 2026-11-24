from django.db import transaction

from billing.models import Payment, ReferralReward, Subscription
from billing.tasks import provision_subscription_to_panels

from .email_utils import validate_email_domain
from .models import User


class AccountLinkError(ValueError):
    pass


@transaction.atomic
def merge_users(primary: User, secondary: User) -> User:
    """
    Объединяет два аккаунта (secondary переносится в primary и удаляется).
    Все подписки, платежи, рефералы, триал и согласие переносятся на primary.
    """
    if primary.id == secondary.id:
        return primary

    primary = User.objects.select_for_update().get(pk=primary.pk)
    secondary = User.objects.select_for_update().get(pk=secondary.pk)

    Subscription.objects.filter(user=secondary).update(
        user=primary,
        xray_uuid=primary.xray_uuid,
    )
    Payment.objects.filter(user=secondary).update(user=primary)

    # Переносим реферальные награды без нарушения UniqueConstraint(referrer, payment)
    for rw in ReferralReward.objects.filter(referrer=secondary):
        if ReferralReward.objects.filter(referrer=primary, payment=rw.payment).exists():
            rw.delete()
        else:
            rw.referrer = primary
            rw.save(update_fields=["referrer"])
    ReferralReward.objects.filter(referred_user=secondary).update(referred_user=primary)

    User.objects.filter(referred_by=secondary).exclude(pk=primary.pk).update(referred_by=primary)

    tg_id = primary.telegram_id or secondary.telegram_id
    tg_username = primary.telegram_username or secondary.telegram_username
    email = primary.email or secondary.email
    canonical_email = primary.canonical_email or secondary.canonical_email
    has_used_trial = primary.has_used_trial or secondary.has_used_trial
    is_legal_accepted = primary.is_legal_accepted or secondary.is_legal_accepted
    legal_accepted_at = primary.legal_accepted_at or secondary.legal_accepted_at

    referred_by_id = primary.referred_by_id
    if not referred_by_id and secondary.referred_by_id and secondary.referred_by_id != primary.id:
        referred_by_id = secondary.referred_by_id

    # Освобождаем уникальные поля у secondary перед удалением
    secondary.telegram_id = None
    secondary.email = None
    secondary.canonical_email = None
    secondary.save(update_fields=["telegram_id", "email", "canonical_email"])
    secondary.delete()

    primary.telegram_id = tg_id
    primary.telegram_username = tg_username
    primary.email = email
    primary.canonical_email = canonical_email
    primary.has_used_trial = has_used_trial
    primary.is_legal_accepted = is_legal_accepted
    primary.legal_accepted_at = legal_accepted_at
    primary.referred_by_id = referred_by_id
    primary.save()

    active_sub = primary.subscriptions.filter(status=Subscription.Status.ACTIVE).order_by("-expires_at").first()
    if active_sub is not None:
        sub_id_str = str(active_sub.id)
        transaction.on_commit(lambda: provision_subscription_to_panels.delay(sub_id_str))

    return primary


@transaction.atomic
def attach_or_merge_email(user: User, raw_email: str) -> User:
    """
    Привязывает email к пользователю (например, при оплате в Telegram или из /cabinet).
    Если email уже принадлежит веб-аккаунту без telegram_id — автоматически объединяет аккаунты.
    Если email уже привязан к другому telegram_id — бросает AccountLinkError.
    """
    cleaned, canonical = validate_email_domain(raw_email, strict_for_trial=False)
    user = User.objects.select_for_update().get(pk=user.pk)

    if user.canonical_email == canonical:
        return user

    existing = User.objects.select_for_update().filter(canonical_email=canonical).first()
    if existing is not None:
        if existing.id == user.id:
            return user
        if existing.telegram_id and user.telegram_id and existing.telegram_id != user.telegram_id:
            raise AccountLinkError("Этот email уже привязан к другому Telegram-аккаунту.")
        if user.email and existing.email and user.canonical_email != existing.canonical_email:
            raise AccountLinkError("Этот email уже привязан к другому аккаунту.")

        if existing.telegram_id and not user.telegram_id:
            return merge_users(primary=existing, secondary=user)
        return merge_users(primary=user, secondary=existing)

    user.email = cleaned
    user.canonical_email = canonical
    user.save(update_fields=["email", "canonical_email"])
    return user