import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import create_admin
from app.core.rate_limit import rate_limiter
from app.modules.users.service import UserService
from tests.fakes import FakeEmailProvider, FakeGoogleAuthVerifier


@pytest.mark.asyncio
async def test_signup_validation_and_duplicate(client: AsyncClient):
    rate_limiter.reset()

    # 1. Weak password
    res_weak = await client.post(
        "/api/v1/auth/signup",
        json={"email": "user1@example.com", "password": "weak", "display_name": "Test User"},
    )
    assert res_weak.status_code == 422 or res_weak.status_code == 400
    assert res_weak.json()["error"]["code"] in ("weak_password", "validation_error")

    # 2. Valid signup
    res_signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "user1@example.com",
            "password": "SecurePassword123!",
            "display_name": "Test User",
        },
    )
    assert res_signup.status_code == 201
    data = res_signup.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "user1@example.com"
    assert data["user"]["email_verified"] is False

    # 3. Duplicate email (case-insensitive)
    res_dup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "USER1@example.com", "password": "SecurePassword123!"},
    )
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "user_exists"


@pytest.mark.asyncio
async def test_email_verification_flow(
    client: AsyncClient,
    fake_email: FakeEmailProvider,
):
    rate_limiter.reset()
    email = "verify-me@example.com"
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password12345!", "display_name": "Verify Me"},
    )

    token = fake_email.get_last_token_for(email)
    assert token is not None

    # Verify email
    res_verify = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert res_verify.status_code == 200
    assert res_verify.json()["message"] == "Email verified successfully"

    # Single-use: Reusing the same verification token must fail
    res_reuse = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert res_reuse.status_code == 400
    assert res_reuse.json()["error"]["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_login_flow_and_no_user_enumeration(client: AsyncClient):
    rate_limiter.reset()
    email = "login-test@example.com"
    pwd = "ValidPassword123!"

    await client.post("/api/v1/auth/signup", json={"email": email, "password": pwd})

    # Success
    res_success = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert res_success.status_code == 200
    assert "access_token" in res_success.json()

    # Wrong password
    res_wrong_pwd = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "WrongPassword123!"}
    )
    assert res_wrong_pwd.status_code == 401

    # Non-existent email
    res_non_existent = await client.post(
        "/api/v1/auth/login", json={"email": "non-existent@example.com", "password": pwd}
    )
    assert res_non_existent.status_code == 401

    # Exact same error message to prevent user enumeration
    assert res_wrong_pwd.json() == res_non_existent.json()
    assert res_wrong_pwd.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_suspended_user_is_blocked(client: AsyncClient, db_session: AsyncSession):
    rate_limiter.reset()
    email = "suspended@example.com"
    pwd = "Password123!"

    res = await client.post("/api/v1/auth/signup", json={"email": email, "password": pwd})
    token = res.json()["access_token"]

    # Suspend user in DB
    user_service = UserService(db_session)
    user = await user_service.get_by_email(email)
    assert user is not None
    await user_service.repository.update(user, is_suspended=True)
    await db_session.commit()

    # Try login
    res_login = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert res_login.status_code == 403
    assert res_login.json()["error"]["code"] == "account_suspended"

    # Try authenticated request
    res_me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 403
    assert res_me.json()["error"]["code"] == "account_suspended"


@pytest.mark.asyncio
async def test_google_auth_flow(client: AsyncClient, fake_google: FakeGoogleAuthVerifier):
    rate_limiter.reset()

    # 1. Valid Google login for new user
    fake_google.register_token(
        "valid-google-token-1",
        {
            "sub": "google-sub-1001",
            "email": "googlenew@example.com",
            "email_verified": True,
            "name": "Google User",
        },
    )
    res1 = await client.post("/api/v1/auth/google", json={"id_token": "valid-google-token-1"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["user"]["email"] == "googlenew@example.com"
    assert data1["user"]["email_verified"] is True

    # 2. Existing password user logs in with Google (linking account)
    pwd_email = "preexisting@example.com"
    await client.post("/api/v1/auth/signup", json={"email": pwd_email, "password": "Password123!"})

    fake_google.register_token(
        "valid-google-token-2",
        {
            "sub": "google-sub-1002",
            "email": pwd_email,
            "email_verified": True,
            "name": "Preexisting User",
        },
    )
    res2 = await client.post("/api/v1/auth/google", json={"id_token": "valid-google-token-2"})
    assert res2.status_code == 200
    assert res2.json()["user"]["email"] == pwd_email

    # 3. Unverified Google email rejected
    fake_google.register_token(
        "unverified-google-token",
        {"sub": "google-sub-1003", "email": "unverified@example.com", "email_verified": False},
    )
    res3 = await client.post("/api/v1/auth/google", json={"id_token": "unverified-google-token"})
    assert res3.status_code == 400
    assert res3.json()["error"]["code"] == "unverified_google_email"

    # 4. Invalid token
    res4 = await client.post("/api/v1/auth/google", json={"id_token": "bad-token-xyz"})
    assert res4.status_code == 401
    assert res4.json()["error"]["code"] == "invalid_google_token"


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection(client: AsyncClient):
    rate_limiter.reset()
    res_signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "rotation@example.com", "password": "Password123!"},
    )
    refresh_token_v1 = res_signup.json()["refresh_token"]

    # 1. Legitimate rotation: v1 -> v2
    res_rot = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token_v1})
    assert res_rot.status_code == 200
    refresh_token_v2 = res_rot.json()["refresh_token"]
    assert refresh_token_v1 != refresh_token_v2

    # 2. Reuse of rotated v1 token: should trigger reuse detection and revoke the entire token family!
    res_reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token_v1})
    assert res_reuse.status_code == 401
    assert res_reuse.json()["error"]["code"] == "token_compromised"

    # 3. Now v2 is also invalidated because the family was revoked!
    res_v2_after_compromise = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token_v2}
    )
    assert res_v2_after_compromise.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient, fake_email: FakeEmailProvider):
    rate_limiter.reset()
    email = "resetpwd@example.com"
    pwd1 = "InitialPassword123!"
    pwd2 = "NewSecurePassword456!"

    res_signup = await client.post("/api/v1/auth/signup", json={"email": email, "password": pwd1})
    initial_refresh = res_signup.json()["refresh_token"]

    # Request reset
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = fake_email.get_last_token_for(email)
    assert token is not None

    # Reset password
    res_reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": pwd2}
    )
    assert res_reset.status_code == 200

    # Old password no longer works
    res_old_login = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd1})
    assert res_old_login.status_code == 401

    # New password works
    res_new_login = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd2})
    assert res_new_login.status_code == 200

    # Reset token cannot be reused
    res_reuse = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "AnotherPwd789!"}
    )
    assert res_reuse.status_code == 400

    # Existing refresh tokens were revoked upon password reset
    res_old_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": initial_refresh}
    )
    assert res_old_refresh.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoints_and_account_deletion(client: AsyncClient):
    rate_limiter.reset()
    email = "me-test@example.com"
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "display_name": "Original Name"},
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /me
    res_get = await client.get("/api/v1/me", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["display_name"] == "Original Name"

    # 2. PATCH /me
    res_patch = await client.patch(
        "/api/v1/me", headers=headers, json={"display_name": "Updated Name"}
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["display_name"] == "Updated Name"

    # 3. GET /me/export
    res_export = await client.get("/api/v1/me/export", headers=headers)
    assert res_export.status_code == 200
    assert "user" in res_export.json()
    assert "export_generated_at" in res_export.json()

    # 4. DELETE /me
    res_del = await client.delete("/api/v1/me", headers=headers)
    assert res_del.status_code == 200

    # Immediate access revocation
    res_after_del = await client.get("/api/v1/me", headers=headers)
    assert res_after_del.status_code == 401
    assert res_after_del.json()["error"]["code"] == "account_deleted"


@pytest.mark.asyncio
async def test_cli_create_admin(db_session: AsyncSession):
    email = "cli-admin@inzar.app"
    pwd = "AdminSecurePassword123!"
    await create_admin(email, pwd, "Root Admin", session=db_session)  # type: ignore[arg-type]

    user_service = UserService(db_session)
    admin = await user_service.get_by_email(email)
    assert admin is not None
    assert admin.role == "admin"
    assert admin.display_name == "Root Admin"
    assert admin.email_verified_at is not None


@pytest.mark.asyncio
async def test_role_guard_matrix(client: AsyncClient, db_session: AsyncSession):
    rate_limiter.reset()

    # Create regular user, moderator, and admin
    user_service = UserService(db_session)
    reg_user = await user_service.create_user(email="regular@example.com", role="user")
    mod_user = await user_service.create_user(email="moderator@example.com", role="moderator")
    admin_user = await user_service.create_user(email="admin@example.com", role="admin")

    from app.core.security import create_access_token

    token_reg = create_access_token(str(reg_user.id), "user")
    token_mod = create_access_token(str(mod_user.id), "moderator")
    token_admin = create_access_token(str(admin_user.id), "admin")

    from fastapi import APIRouter, Depends

    from app.modules.auth.dependencies import require_admin, require_moderator, require_user
    from app.modules.users.models import User

    test_router = APIRouter()

    @test_router.get("/test-reg")
    async def route_reg(_: User = Depends(require_user)):
        return {"ok": True}

    @test_router.get("/test-mod")
    async def route_mod(_: User = Depends(require_moderator)):
        return {"ok": True}

    @test_router.get("/test-admin")
    async def route_admin(_: User = Depends(require_admin)):
        return {"ok": True}

    from app.db.session import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.include_router(test_router)

    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Anonymous fails on all
        assert (await ac.get("/test-reg")).status_code == 401
        assert (await ac.get("/test-mod")).status_code == 401
        assert (await ac.get("/test-admin")).status_code == 401

        # Regular user
        h_reg = {"Authorization": f"Bearer {token_reg}"}
        assert (await ac.get("/test-reg", headers=h_reg)).status_code == 200
        assert (await ac.get("/test-mod", headers=h_reg)).status_code == 403
        assert (await ac.get("/test-admin", headers=h_reg)).status_code == 403

        # Moderator
        h_mod = {"Authorization": f"Bearer {token_mod}"}
        assert (await ac.get("/test-reg", headers=h_mod)).status_code == 200
        assert (await ac.get("/test-mod", headers=h_mod)).status_code == 200
        assert (await ac.get("/test-admin", headers=h_mod)).status_code == 403

        # Admin
        h_admin = {"Authorization": f"Bearer {token_admin}"}
        assert (await ac.get("/test-reg", headers=h_admin)).status_code == 200
        assert (await ac.get("/test-mod", headers=h_admin)).status_code == 200
        assert (await ac.get("/test-admin", headers=h_admin)).status_code == 200
