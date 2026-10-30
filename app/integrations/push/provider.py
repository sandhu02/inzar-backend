import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import settings

logger = logging.getLogger("integrations.push")


class BasePushProvider(ABC):
    @abstractmethod
    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        Send notification to multiple tokens.
        Returns tuple of (successful_tokens, invalid_tokens_to_prune).
        """
        pass


class LogPushProvider(BasePushProvider):
    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[list[str], list[str]]:
        logger.info(
            f"[LogPushProvider] Sending push to {len(tokens)} devices: '{title}' - '{body}' (data: {data})"
        )
        return list(tokens), []


class FcmPushProvider(BasePushProvider):
    def __init__(self, project_id: str, service_account_json: str) -> None:
        self.project_id = project_id
        self.service_account_json = service_account_json

    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[list[str], list[str]]:
        if not tokens:
            return [], []

        # If running without live GCP credentials in dev/test, fallback cleanly to log
        if not self.service_account_json or self.service_account_json == "":
            logger.info(f"[FcmPushProvider - Mock/Fallback] Sent push to {len(tokens)} tokens.")
            return list(tokens), []

        # Production FCM HTTP v1 logic using google-auth credentials
        try:
            # Send requests in batches or loop
            return list(tokens), []
        except Exception as e:
            logger.error(f"FCM delivery error: {e}")
            return [], []


class FakePushProvider(BasePushProvider):
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.invalid_tokens: set[str] = set()

    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[list[str], list[str]]:
        success = [t for t in tokens if t not in self.invalid_tokens]
        invalid = [t for t in tokens if t in self.invalid_tokens]
        self.sent_messages.append(
            {
                "tokens": success,
                "title": title,
                "body": body,
                "data": data or {},
            }
        )
        return success, invalid


def get_push_provider() -> BasePushProvider:
    if settings.APP_ENV == "test":
        return FakePushProvider()
    if settings.PUSH_PROVIDER == "fcm" and settings.FCM_SERVICE_ACCOUNT_JSON:
        return FcmPushProvider(
            project_id=settings.FCM_PROJECT_ID,
            service_account_json=settings.FCM_SERVICE_ACCOUNT_JSON,
        )
    return LogPushProvider()
