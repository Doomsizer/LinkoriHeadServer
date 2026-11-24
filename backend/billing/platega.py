import secrets

import httpx
from django.conf import settings


class PlategaError(Exception):
    pass


# Коды методов оплаты Platega
PLATEGA_METHOD_SBP = 2
PLATEGA_METHOD_CRYPTO = 13

METHOD_CODE_MAP = {
    "sbp": PLATEGA_METHOD_SBP,
    "crypto": PLATEGA_METHOD_CRYPTO,
}


def verify_platega_headers(headers) -> bool:
    merchant_id = (headers.get("X-MerchantId") or "").strip()
    secret = (headers.get("X-Secret") or "").strip()
    expected_id = (settings.PLATEGA_MERCHANT_ID or "").strip()
    expected_secret = (settings.PLATEGA_SECRET or "").strip()
    if not expected_id or not expected_secret:
        return False
    return secrets.compare_digest(merchant_id, expected_id) and secrets.compare_digest(
        secret, expected_secret
    )


def _platega_headers() -> dict[str, str]:
    if not settings.PLATEGA_MERCHANT_ID or not settings.PLATEGA_SECRET:
        raise PlategaError("Платежный шлюз Platega не настроен (отсутствуют MerchantId / Secret).")
    return {
        "X-MerchantId": settings.PLATEGA_MERCHANT_ID.strip(),
        "X-Secret": settings.PLATEGA_SECRET.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_platega_transaction(
    payment_id: str,
    amount_kopeks: int,
    payment_method_key: str,
    description: str,
    user_email: str,
    user_id_str: str,
    user_name: str,
    return_url: str,
    failed_url: str,
    timeout: float = 15.0,
) -> dict:
    method_code = METHOD_CODE_MAP.get(payment_method_key.lower())
    if method_code is None:
        raise PlategaError(f"Неподдерживаемый метод оплаты: {payment_method_key}")

    amount_rub = round(amount_kopeks / 100, 2)
    payload = {
        "paymentMethod": method_code,
        "paymentDetails": {
            "amount": int(amount_rub) if amount_rub.is_integer() else amount_rub,
            "currency": "RUB",
        },
        "description": description[:250],
        "return": return_url,
        "failedUrl": failed_url,
        "payload": payment_id,
        "metadata": {
            "user_email": user_email,
            "userId": user_id_str,
            "userName": user_name[:64],
        },
    }

    url = f"{settings.PLATEGA_API_URL}/transaction/process"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=_platega_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        body_text = exc.response.text[:300] if exc.response is not None else str(exc)
        raise PlategaError(f"Ошибка Platega ({exc.response.status_code}): {body_text}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise PlategaError(f"Ошибка соединения с Platega: {exc}") from exc

    tx_id = str(data.get("transactionId") or "").strip()
    redirect_url = str(data.get("redirect") or "").strip()
    if not tx_id or not redirect_url:
        raise PlategaError("Platega вернула неполный ответ при создании транзакции.")

    return {
        "transaction_id": tx_id,
        "redirect_url": redirect_url,
        "status": str(data.get("status") or "PENDING").upper(),
        "raw": data,
    }


def fetch_platega_transaction_status(transaction_id: str, timeout: float = 10.0) -> str:
    url = f"{settings.PLATEGA_API_URL}/transaction/{transaction_id}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=_platega_headers())
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PlategaError(f"Ошибка проверки статуса в Platega: {exc}") from exc

    return str(data.get("status") or "").upper()