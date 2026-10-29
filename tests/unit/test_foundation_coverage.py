from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    RateLimitExceededError,
    UnauthorizedError,
    register_exception_handlers,
)
from app.core.rate_limit import get_client_ip, rate_limiter
from app.core.security import decode_access_token
from app.db.session import check_db_health, get_db
from app.main import create_app


@pytest.mark.asyncio
async def test_api_v1_info():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/info")
        assert response.status_code == 200
        assert response.json()["name"] == "Inzar API"
        assert response.json()["version"] == "v1"


@pytest.mark.asyncio
async def test_all_custom_error_types():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/not-found")
    async def route_not_found():
        raise NotFoundError("custom item not found")

    @test_app.get("/conflict")
    async def route_conflict():
        raise ConflictError("item already exists")

    @test_app.get("/forbidden")
    async def route_forbidden():
        raise ForbiddenError("admin role required")

    @test_app.get("/gone")
    async def route_gone():
        raise GoneError("item has expired")

    @test_app.get("/unauthorized")
    async def route_unauthorized():
        raise UnauthorizedError("token invalid")

    @test_app.get("/rate-limit")
    async def route_rate_limit():
        raise RateLimitExceededError("too fast")

    @test_app.get("/unhandled-server-error")
    async def route_server_error():
        raise RuntimeError("database exploded")

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res1 = await ac.get("/not-found")
        assert res1.status_code == 404
        assert res1.json()["error"]["code"] == "not_found"

        res2 = await ac.get("/conflict")
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] == "conflict"

        res3 = await ac.get("/forbidden")
        assert res3.status_code == 403
        assert res3.json()["error"]["code"] == "forbidden"

        res4 = await ac.get("/gone")
        assert res4.status_code == 410
        assert res4.json()["error"]["code"] == "gone"

        res5 = await ac.get("/unauthorized")
        assert res5.status_code == 401
        assert res5.json()["error"]["code"] == "unauthorized"

        res6 = await ac.get("/rate-limit")
        assert res6.status_code == 429
        assert res6.json()["error"]["code"] == "rate_limit_exceeded"

        res7 = await ac.get("/unhandled-server-error")
        assert res7.status_code == 500
        assert res7.json()["error"]["code"] == "internal_server_error"


@pytest.mark.asyncio
async def test_validation_error_handler():
    from pydantic import BaseModel

    test_app = FastAPI()
    register_exception_handlers(test_app)

    class Payload(BaseModel):
        count: int

    @test_app.post("/validate")
    async def route_validate(payload: Payload):
        return {"count": payload.count}

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/validate", json={"count": "not-an-int"})
        assert res.status_code == 422
        data = res.json()
        assert data["error"]["code"] == "validation_error"
        assert "details" in data["error"]
        assert len(data["error"]["details"]["errors"]) > 0


@pytest.mark.asyncio
async def test_rate_limit_dependency():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    rate_limiter.reset()

    @test_app.get("/rate-limited")
    async def route_rate_limited():
        # manual dependency call simulation
        await rate_limiter.check("ip:127.0.0.1", max_requests=2, window_seconds=60)
        return {"status": "ok"}

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res1 = await ac.get("/rate-limited")
        assert res1.status_code == 200

        res2 = await ac.get("/rate-limited")
        assert res2.status_code == 200

        res3 = await ac.get("/rate-limited")
        assert res3.status_code == 429
        assert res3.json()["error"]["code"] == "rate_limit_exceeded"


def test_get_client_ip():
    mock_req = MagicMock()
    mock_req.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
    assert get_client_ip(mock_req) == "203.0.113.195"

    mock_req2 = MagicMock()
    mock_req2.headers = {}
    mock_req2.client.host = "192.168.1.100"
    assert get_client_ip(mock_req2) == "192.168.1.100"


@pytest.mark.asyncio
async def test_get_db_session():
    # Test real db session generator against local test PostGIS database
    gen = get_db()
    session = await anext(gen)
    assert session is not None
    # close generator
    try:
        await anext(gen)
    except StopAsyncIteration:
        pass


@pytest.mark.asyncio
async def test_real_db_health():
    healthy, msg = await check_db_health()
    assert healthy is True
    assert "PostGIS" in msg


def test_security_invalid_tokens():
    with pytest.raises(UnauthorizedError):
        decode_access_token("completely.invalid.token")
