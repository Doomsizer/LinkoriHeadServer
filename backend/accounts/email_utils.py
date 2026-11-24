BLOCKED_EMAIL_DOMAINS: set[str] = {
    # Rambler
    "rambler.ru",
    "lenta.ru",
    "autorambler.ru",
    "myrambler.ru",
    "ro.ru",
    "rambler.ua",
    # Proton
    "proton.me",
    "protonmail.com",
    "protonmail.ch",
    "pm.me",
    # Tuta / популярные одноразовые домены
    "tuta.io",
    "tuta.com",
    "tutanota.com",
    "tutanota.de",
    "temp-mail.org",
    "temp-mail.io",
    "tempmail.com",
    "tempmail.plus",
    "10minutemail.com",
    "10minutemail.net",
    "guerrillamail.com",
    "guerrillamail.info",
    "sharklasers.com",
    "mailinator.com",
    "yopmail.com",
    "trashmail.com",
    "getnada.com",
    "dispostable.com",
    "maildrop.cc",
    "mintemail.com",
    "mohmal.com",
    "dropmail.me",
    "emailondeck.com",
    "fakeinbox.com",
    "throwawaymail.com",
    "mail.tm",
    "mail.gw",
}

TRUSTED_TRIAL_DOMAINS: set[str] = {
    "gmail.com",
    "googlemail.com",
    "yandex.ru",
    "ya.ru",
    "yandex.com",
    "yandex.by",
    "yandex.kz",
    "mail.ru",
    "bk.ru",
    "list.ru",
    "inbox.ru",
    "internet.ru",
    "vk.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "ukr.net",
}

GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}
YANDEX_DOMAINS = {"yandex.ru", "ya.ru", "yandex.com", "yandex.by", "yandex.kz"}
PLUS_TAG_DOMAINS = GMAIL_DOMAINS | YANDEX_DOMAINS | {
    "mail.ru",
    "bk.ru",
    "list.ru",
    "inbox.ru",
    "internet.ru",
    "icloud.com",
    "me.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
}


class EmailValidationError(ValueError):
    pass


def normalize_email_raw(email: str) -> str:
    return (email or "").strip().lower()


def canonicalize_email(email: str) -> str:
    cleaned = normalize_email_raw(email)
    if "@" not in cleaned:
        return cleaned
    local, domain = cleaned.rsplit("@", 1)

    if domain in GMAIL_DOMAINS:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    elif domain in YANDEX_DOMAINS:
        local = local.split("+", 1)[0]
        domain = "yandex.ru"
    elif domain in PLUS_TAG_DOMAINS:
        local = local.split("+", 1)[0]

    return f"{local}@{domain}"


def validate_email_domain(email: str, strict_for_trial: bool = False) -> tuple[str, str]:
    cleaned = normalize_email_raw(email)
    if "@" not in cleaned:
        raise EmailValidationError("Укажите корректный email.")

    _, domain = cleaned.rsplit("@", 1)
    if domain in BLOCKED_EMAIL_DOMAINS or "tempmail" in domain or "temp-mail" in domain:
        raise EmailValidationError(
            "Почтовые сервисы Rambler, Proton и временные почты не поддерживаются."
        )

    if strict_for_trial and domain not in TRUSTED_TRIAL_DOMAINS:
        raise EmailValidationError(
            "Для пробного периода используйте популярный почтовый сервис "
            "(Gmail, Яндекс, Mail.ru, iCloud, Outlook)."
        )

    return cleaned, canonicalize_email(cleaned)