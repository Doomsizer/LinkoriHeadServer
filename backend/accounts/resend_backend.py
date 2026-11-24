import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendApiEmailBackend(BaseEmailBackend):
    """
    Отправляет письма через HTTPS API Resend (порт 443),
    чтобы не зависеть от заблокированных SMTP-портов 25/465/587 на VPS.
    """

    def send_messages(self, email_messages):
        api_key = (
            getattr(settings, "RESEND_API_KEY", "")
            or getattr(settings, "EMAIL_HOST_PASSWORD", "")
        ).strip()
        if not api_key:
            if not self.fail_silently:
                raise RuntimeError("Не задан API-ключ Resend (RESEND_API_KEY / EMAIL_HOST_PASSWORD).")
            return 0

        sent_count = 0
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=15.0) as client:
            for msg in email_messages:
                if not msg.to:
                    continue
                payload = {
                    "from": msg.from_email or settings.DEFAULT_FROM_EMAIL,
                    "to": list(msg.to),
                    "subject": msg.subject,
                    "text": msg.body,
                }
                if msg.cc:
                    payload["cc"] = list(msg.cc)
                if msg.bcc:
                    payload["bcc"] = list(msg.bcc)
                if msg.reply_to:
                    payload["reply_to"] = list(msg.reply_to)

                try:
                    resp = client.post(
                        "https://api.resend.com/emails",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    sent_count += 1
                except Exception:
                    if not self.fail_silently:
                        raise
        return sent_count