from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.email.provider import (
    ConsoleEmailProvider,
    ResendEmailProvider,
    get_email_provider,
)


@pytest.mark.asyncio
async def test_console_email_provider():
    provider = ConsoleEmailProvider()
    ok = await provider.send_verification_email("user@example.com", "token123")
    assert ok is True
    assert len(provider.sent_emails) == 1
    assert provider.sent_emails[0]["to"] == "user@example.com"

    ok_reset = await provider.send_password_reset_email("user@example.com", "reset123")
    assert ok_reset is True
    assert len(provider.sent_emails) == 2


@pytest.mark.asyncio
async def test_resend_email_provider():
    # Without api key -> logs warning and returns False
    empty_provider = ResendEmailProvider(api_key="", from_address="test@inzar.app")
    assert await empty_provider.send_email("to@example.com", "Sub", "<p>hi</p>", "hi") is False

    # With mocked httpx
    provider = ResendEmailProvider(api_key="re_12345", from_address="test@inzar.app")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        ok = await provider.send_email("to@example.com", "Sub", "<p>hi</p>", "hi")
        assert ok is True

    # Provider factory
    assert get_email_provider() is not None
