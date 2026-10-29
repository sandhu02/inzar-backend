from typing import Any

from app.core.errors import UnauthorizedError
from app.integrations.email.provider import BaseEmailProvider
from app.integrations.google_auth.verifier import BaseGoogleAuthVerifier


class FakeEmailProvider(BaseEmailProvider):
    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        self.sent_emails.append(
            {
                "to": to_email,
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
        )
        return True

    def get_last_token_for(self, email: str) -> str | None:
        for mail in reversed(self.sent_emails):
            if mail["to"] == email:
                # Extract token from text: "token is: <token>"
                for line in mail["text"].splitlines():
                    if "token is:" in line:
                        return line.split("token is:")[1].strip()
        return None


class FakeGoogleAuthVerifier(BaseGoogleAuthVerifier):
    def __init__(self) -> None:
        self.mock_tokens: dict[str, dict[str, Any]] = {}

    def register_token(self, token: str, claims: dict[str, Any]) -> None:
        self.mock_tokens[token] = claims

    async def verify_id_token(self, token: str) -> dict[str, Any]:
        if token in self.mock_tokens:
            return self.mock_tokens[token]
        raise UnauthorizedError("Invalid fake token", code="invalid_google_token")
