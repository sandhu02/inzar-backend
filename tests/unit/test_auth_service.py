from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, UnauthorizedError
from app.modules.auth.schemas import (
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService
from tests.fakes import FakeEmailProvider, FakeGoogleAuthVerifier


@pytest.fixture
def auth_service_unit(
    db_session: AsyncSession,
    fake_email: FakeEmailProvider,
    fake_google: FakeGoogleAuthVerifier,
) -> AuthService:
    return AuthService(
        session=db_session,
        email_provider=fake_email,
        google_verifier=fake_google,
    )


@pytest.mark.asyncio
async def test_auth_service_resend_verification_and_forgot_password(
    auth_service_unit: AuthService,
    fake_email: FakeEmailProvider,
):
    # 1. Resend verification for non-existent email (should not raise)
    await auth_service_unit.resend_verification("nonexistent@example.com")
    assert fake_email.get_last_token_for("nonexistent@example.com") is None

    # 2. Resend verification for existing unverified user
    await auth_service_unit.signup(
        SignupRequest(email="unverified-user@example.com", password="Password123!")
    )
    await auth_service_unit.resend_verification("unverified-user@example.com")
    token = fake_email.get_last_token_for("unverified-user@example.com")
    assert token is not None

    # 3. Forgot password for non-existent email (should not raise)
    await auth_service_unit.forgot_password("unknown@example.com")


@pytest.mark.asyncio
async def test_auth_service_verify_email_edge_cases(
    auth_service_unit: AuthService,
    db_session: AsyncSession,
    fake_email: FakeEmailProvider,
):
    # Invalid token
    with pytest.raises(BadRequestError):
        await auth_service_unit.verify_email(VerifyEmailRequest(token="completely-bogus-token"))

    # Expired token
    await auth_service_unit.signup(
        SignupRequest(email="expired-token@example.com", password="Password123!")
    )
    token = fake_email.get_last_token_for("expired-token@example.com")
    assert token is not None

    # Manually expire the token in DB
    token_hash = auth_service_unit._hash_token(token)
    db_token = await auth_service_unit.auth_repo.get_email_token_by_hash(
        token_hash, purpose="verify"
    )
    assert db_token is not None
    db_token.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await auth_service_unit.verify_email(VerifyEmailRequest(token=token))


@pytest.mark.asyncio
async def test_auth_service_logout_and_refresh_errors(
    auth_service_unit: AuthService,
    db_session: AsyncSession,
):
    # Logout with non-existent token (should not raise)
    await auth_service_unit.logout(LogoutRequest(refresh_token="bogus-refresh-token"))

    # Refresh with non-existent token
    with pytest.raises(UnauthorizedError):
        await auth_service_unit.refresh_tokens(
            RefreshTokenRequest(refresh_token="nonexistent-refresh")
        )

    # Refresh with expired token
    res = await auth_service_unit.signup(
        SignupRequest(email="refresh-exp@example.com", password="Password123!")
    )
    token_hash = auth_service_unit._hash_token(res.refresh_token)
    db_token = await auth_service_unit.auth_repo.get_refresh_token_by_hash(token_hash)
    assert db_token is not None
    db_token.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    with pytest.raises(UnauthorizedError):
        await auth_service_unit.refresh_tokens(RefreshTokenRequest(refresh_token=res.refresh_token))


@pytest.mark.asyncio
async def test_auth_service_google_missing_claims(
    auth_service_unit: AuthService,
    fake_google: FakeGoogleAuthVerifier,
):
    fake_google.register_token(
        "missing-sub", {"email": "no-sub@example.com", "email_verified": True}
    )
    with pytest.raises(UnauthorizedError):
        await auth_service_unit.google_login(GoogleLoginRequest(id_token="missing-sub"))


@pytest.mark.asyncio
async def test_auth_service_reset_password_errors(
    auth_service_unit: AuthService,
    fake_email: FakeEmailProvider,
):
    with pytest.raises(BadRequestError):
        await auth_service_unit.reset_password(
            ResetPasswordRequest(token="bad-token", new_password="NewPassword123!")
        )


@pytest.mark.asyncio
async def test_auth_service_signup_duplicate_and_login_paths(
    auth_service_unit: AuthService,
    db_session: AsyncSession,
):
    # Duplicate signup raises ConflictError
    await auth_service_unit.signup(SignupRequest(email="dup@example.com", password="Password123!"))
    from app.core.errors import ConflictError, ForbiddenError

    with pytest.raises(ConflictError):
        await auth_service_unit.signup(
            SignupRequest(email="dup@example.com", password="Password123!")
        )

    # Login success
    login_res = await auth_service_unit.login(
        LoginRequest(email="dup@example.com", password="Password123!")
    )
    assert login_res.access_token is not None

    # Login wrong password
    with pytest.raises(UnauthorizedError):
        await auth_service_unit.login(
            LoginRequest(email="dup@example.com", password="WrongPassword123!")
        )

    # Login suspended user
    user = await auth_service_unit.user_service.get_by_email("dup@example.com")
    assert user is not None
    await auth_service_unit.user_service.repository.update(user, is_suspended=True)
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await auth_service_unit.login(
            LoginRequest(email="dup@example.com", password="Password123!")
        )


@pytest.mark.asyncio
async def test_auth_service_google_login_variants(
    auth_service_unit: AuthService,
    fake_google: FakeGoogleAuthVerifier,
    db_session: AsyncSession,
):
    from app.core.errors import ForbiddenError

    # Unverified email raises BadRequestError
    fake_google.register_token(
        "unverified-token", {"sub": "sub-123", "email": "unv@example.com", "email_verified": False}
    )
    with pytest.raises(BadRequestError):
        await auth_service_unit.google_login(GoogleLoginRequest(id_token="unverified-token"))

    # New user via Google
    fake_google.register_token(
        "valid-google",
        {"sub": "sub-new", "email": "googlenewbie@example.com", "email_verified": True},
    )
    res_new = await auth_service_unit.google_login(GoogleLoginRequest(id_token="valid-google"))
    assert res_new.user.email == "googlenewbie@example.com"

    # Match by google_sub
    res_sub = await auth_service_unit.google_login(GoogleLoginRequest(id_token="valid-google"))
    assert res_sub.user.email == "googlenewbie@example.com"

    # Suspended google user
    user = await auth_service_unit.user_service.get_by_google_sub("sub-new")
    assert user is not None
    await auth_service_unit.user_service.repository.update(user, is_suspended=True)
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await auth_service_unit.google_login(GoogleLoginRequest(id_token="valid-google"))


@pytest.mark.asyncio
async def test_auth_service_refresh_and_reset_full_flow(
    auth_service_unit: AuthService,
    fake_email: FakeEmailProvider,
    db_session: AsyncSession,
):
    # Signup
    signup_res = await auth_service_unit.signup(
        SignupRequest(email="refreshfull@example.com", password="Password123!")
    )

    # Refresh success
    ref_res = await auth_service_unit.refresh_tokens(
        RefreshTokenRequest(refresh_token=signup_res.refresh_token)
    )
    assert ref_res.refresh_token != signup_res.refresh_token

    # Reuse old token -> revokes family
    with pytest.raises(UnauthorizedError) as exc:
        await auth_service_unit.refresh_tokens(
            RefreshTokenRequest(refresh_token=signup_res.refresh_token)
        )
    assert exc.value.code == "token_compromised"

    # Logout
    await auth_service_unit.logout(LogoutRequest(refresh_token=ref_res.refresh_token))

    # Resend verification when already verified
    user = await auth_service_unit.user_service.get_by_email("refreshfull@example.com")
    assert user is not None
    await auth_service_unit.user_service.set_email_verified(user.id)
    await auth_service_unit.resend_verification("refreshfull@example.com")

    # Forgot password & Reset password success
    await auth_service_unit.forgot_password("refreshfull@example.com")
    reset_tok = fake_email.get_last_token_for("refreshfull@example.com")
    assert reset_tok is not None

    await auth_service_unit.reset_password(
        ResetPasswordRequest(token=reset_tok, new_password="NewSecurePassword123!")
    )

    # Verify new password can login
    login_res = await auth_service_unit.login(
        LoginRequest(email="refreshfull@example.com", password="NewSecurePassword123!")
    )
    assert login_res.access_token is not None
