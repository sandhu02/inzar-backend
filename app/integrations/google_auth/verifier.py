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
        self.allowed_client_ids = allowed_client_ids

    async def verify_id_token(self, token: str) -> dict[str, Any]:
        try:
            # Synchronous verification call via request adapter
            req = requests.Request()
            # If client IDs configured, verify audience
            audience = self.allowed_client_ids[0] if self.allowed_client_ids else None
            claims = id_token.verify_oauth2_token(token, req, audience=audience)  # type: ignore[no-untyped-call]
            return dict(claims)
        except Exception as exc:
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
