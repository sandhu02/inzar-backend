import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("inzar.integrations.email")


class BaseEmailProvider(ABC):
    @abstractmethod
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send an email."""
        pass

    async def send_verification_email(self, to_email: str, token: str) -> bool:
        subject = "Verify your email - Inzar"
        text = f"Your email verification token is: {token}\nThis token will expire in {settings.EMAIL_TOKEN_TTL_HOURS} hours."
        html = f"<p>Your email verification token is: <strong>{token}</strong></p><p>This token will expire in {settings.EMAIL_TOKEN_TTL_HOURS} hours.</p>"
        return await self.send_email(to_email, subject, html, text)

    async def send_password_reset_email(self, to_email: str, token: str) -> bool:
        subject = "Reset your password - Inzar"
        text = f"Your password reset token is: {token}\nThis token will expire in {settings.EMAIL_TOKEN_TTL_HOURS} hours."
        html = f"<p>Your password reset token is: <strong>{token}</strong></p><p>This token will expire in {settings.EMAIL_TOKEN_TTL_HOURS} hours.</p>"
        return await self.send_email(to_email, subject, html, text)


class ConsoleEmailProvider(BaseEmailProvider):
    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        email_data = {
            "to": to_email,
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }
        self.sent_emails.append(email_data)
        logger.info(
            f"[Console Email] To: {to_email} | Subject: {subject} | Content: {text_content}"
        )
        return True


class ResendEmailProvider(BaseEmailProvider):
    def __init__(self, api_key: str, from_address: str) -> None:
        self.api_key = api_key
        self.from_address = from_address
        self.endpoint = "https://api.resend.com/emails"

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        if not self.api_key:
            logger.warning("Resend API key not set; falling back to log.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self.from_address,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(self.endpoint, json=payload, headers=headers, timeout=10.0)
                if res.status_code in (200, 201):
                    return True
                logger.error(
                    f"Resend email sending failed with status {res.status_code}: {res.text}"
                )
                return False
            except Exception as exc:
                logger.error(f"Resend error: {exc}")
                return False


# Singleton instances
_console_provider = ConsoleEmailProvider()


def get_email_provider() -> BaseEmailProvider:
    if settings.EMAIL_PROVIDER == "resend":
        return ResendEmailProvider(settings.RESEND_API_KEY, settings.EMAIL_FROM)
    return _console_provider
