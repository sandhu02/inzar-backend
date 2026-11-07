from abc import ABC, abstractmethod
from typing import Any

from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.config import settings
from app.core.errors import UnauthorizedError


class BaseGoogleAuthVerifier(ABC):
    @abstractmethod
    async def verify_id_token(self, token: str) -> dict[str, Any]:
        """Verify Google ID token and return claims dict."""
        pass


class GoogleAuthVerifier(BaseGoogleAuthVerifier):
    def __init__(self, allowed_client_ids: list[str]) -> None:
        self.allowed_client_ids = [
            cid for cid in allowed_client_ids
            if cid and not cid.startswith("your-google-client-id")
        ]

    async def verify_id_token(self, token: str) -> dict[str, Any]:
        # Support development/testing tokens when in development environment
        if settings.APP_ENV == "development" and (
            token.startswith("dev_")
            or token.startswith("test_")
            or token.startswith("google_")
        ):
            # Extract email or ID if formatted
            email = "google.user@example.com"
            if "@" in token:
                parts = token.split("_")
                for p in parts:
                    if "@" in p:
                        email = p
            return {
                "sub": f"google_sub_{abs(hash(token)) % 1000000000}",
                "email": email,
                "email_verified": True,
                "name": "Google User",
            }

        try:
            # Synchronous verification call via request adapter
            req = requests.Request()
            # If client IDs configured, verify audience
            audience = self.allowed_client_ids[0] if self.allowed_client_ids else None
            claims = id_token.verify_oauth2_token(token, req, audience=audience)  # type: ignore[no-untyped-call]
            return dict(claims)
        except Exception as exc:
            # If audience check failed because no client ID was matched, try without audience in dev
            if settings.APP_ENV == "development":
                try:
                    req = requests.Request()
                    claims = id_token.verify_oauth2_token(token, req)  # type: ignore[no-untyped-call]
                    return dict(claims)
                except Exception:
                    pass

            raise UnauthorizedError(
                message="Invalid or expired Google ID token",
                code="invalid_google_token",
            ) from exc


_allowed_ids = (
    settings.GOOGLE_CLIENT_IDS
    if isinstance(settings.GOOGLE_CLIENT_IDS, list)
    else [settings.GOOGLE_CLIENT_IDS]
)
_default_verifier = GoogleAuthVerifier(_allowed_ids)


def get_google_auth_verifier() -> BaseGoogleAuthVerifier:
    return _default_verifier
