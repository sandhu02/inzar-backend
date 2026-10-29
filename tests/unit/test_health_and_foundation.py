from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import BadRequestError
from app.core.geo import (
    fuzz_coordinates,
    haversine_distance_m,
    validate_bbox,
    validate_coordinates,
)
from app.core.pagination import CursorParams, decode_cursor, encode_cursor
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.main import create_app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_readyz_success():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.main.check_db_health", return_value=(True, "PostGIS 3.4")):
            response = await ac.get("/readyz")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "healthy"
            assert "PostGIS" in data["postgis"]


@pytest.mark.asyncio
async def test_readyz_failure_when_db_down():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("app.main.check_db_health", return_value=(False, "Connection refused")):
            response = await ac.get("/readyz")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "unreachable"
            assert "error" in data


@pytest.mark.asyncio
async def test_request_id_generated_and_propagated():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Without custom header
        res1 = await ac.get("/healthz")
        assert "x-request-id" in res1.headers
        custom_id = "test-req-id-12345"

        # With custom header
        res2 = await ac.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res2.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_uniform_error_format_on_404():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/non-existent-route-xyz")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "details" in data["error"]
        assert data["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_rate_limiter_in_memory():
    limiter = InMemoryRateLimiter()
    key = "test-user-ip"

    # Allow 3 requests in a 10s window
    allowed1, rem1, _ = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed1 is True
    assert rem1 == 2

    allowed2, rem2, _ = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed2 is True
    assert rem2 == 1

    allowed3, rem3, _ = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed3 is True
    assert rem3 == 0

    # 4th request exceeds limit
    allowed4, rem4, retry_after = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed4 is False
    assert rem4 == 0
    assert retry_after > 0


def test_geo_coordinate_validation():
    validate_coordinates(34.0522, -118.2437)
    with pytest.raises(BadRequestError):
        validate_coordinates(95.0, 0.0)
    with pytest.raises(BadRequestError):
        validate_coordinates(0.0, 195.0)

    validate_bbox(10.0, 20.0, 30.0, 40.0)
    with pytest.raises(BadRequestError):
        validate_bbox(30.0, 20.0, 10.0, 40.0)


def test_geo_fuzzing_determinism_and_distance():
    lat, lon = 37.7749, -122.4194
    seed = "incident-uuid-abc-123"

    fuzzed_lat1, fuzzed_lon1 = fuzz_coordinates(lat, lon, seed=seed, fuzz_distance_m=200.0)
    fuzzed_lat2, fuzzed_lon2 = fuzz_coordinates(lat, lon, seed=seed, fuzz_distance_m=200.0)

    # Determinism: same seed yields identical fuzzed location
    assert fuzzed_lat1 == fuzzed_lat2
    assert fuzzed_lon1 == fuzzed_lon2

    # Different seed yields different fuzzed location
    fuzzed_lat3, fuzzed_lon3 = fuzz_coordinates(
        lat, lon, seed="different-seed", fuzz_distance_m=200.0
    )
    assert (fuzzed_lat1, fuzzed_lon1) != (fuzzed_lat3, fuzzed_lon3)

    # Distance check: should be around ~200 meters (between 160m and 240m)
    dist = haversine_distance_m(lat, lon, fuzzed_lat1, fuzzed_lon1)
    assert 160.0 <= dist <= 245.0


def test_cursor_pagination_helpers():
    payload = {"id": "123", "created_at": "2026-10-30T00:00:00Z"}
    encoded = encode_cursor(payload)
    decoded = decode_cursor(encoded)
    assert decoded == payload

    assert decode_cursor(None) is None
    assert decode_cursor("invalid-base64-string!!") is None

    params = CursorParams(cursor=encoded, limit=50)
    assert params.limit == 50
    assert params.cursor == encoded


def test_security_password_and_jwt():
    pwd = "SecurePassword123!"
    validate_password_strength(pwd)

    with pytest.raises(BadRequestError):
        validate_password_strength("weak")
    with pytest.raises(BadRequestError):
        validate_password_strength("alllowercase123")
    with pytest.raises(BadRequestError):
        validate_password_strength("ALLUPPERCASE123")
    with pytest.raises(BadRequestError):
        validate_password_strength("NoDigitsHere!")

    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

    # JWT
    token = create_access_token(user_id="user-123", role="user")
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "user"
    assert decoded["type"] == "access"
