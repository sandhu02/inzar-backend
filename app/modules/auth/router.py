from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.integrations.email.provider import BaseEmailProvider, get_email_provider
from app.integrations.google_auth.verifier import (
    BaseGoogleAuthVerifier,
    get_google_auth_verifier,
)
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_auth_service(
    session: AsyncSession = Depends(get_db),
    email_provider: BaseEmailProvider = Depends(get_email_provider),
    google_verifier: BaseGoogleAuthVerifier = Depends(get_google_auth_verifier),
) -> AuthService:
    return AuthService(
        session=session,
        email_provider=email_provider,
        google_verifier=google_verifier,
    )


auth_limiter = rate_limit(
    max_requests=settings.RATE_LIMIT_AUTH_PER_MINUTE,
    window_seconds=60,
    key_prefix="auth",
)


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(auth_limiter)],
    summary="Register a new user account with email and password",
)
async def signup(
    request: Request,
    payload: SignupRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user_agent = request.headers.get("user-agent")
    return await auth_service.signup(payload, user_agent=user_agent)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(auth_limiter)],
    summary="Authenticate with email and password",
)
async def login(
    request: Request,
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user_agent = request.headers.get("user-agent")
    return await auth_service.login(payload, user_agent=user_agent)


@router.post(
    "/google",
    response_model=TokenResponse,
    dependencies=[Depends(auth_limiter)],
    summary="Authenticate or register via Google ID token",
)
async def google_login(
    request: Request,
    payload: GoogleLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user_agent = request.headers.get("user-agent")
    return await auth_service.google_login(payload, user_agent=user_agent)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and retrieve new access token",
)
async def refresh(
    request: Request,
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user_agent = request.headers.get("user-agent")
    return await auth_service.refresh_tokens(payload, user_agent=user_agent)


@router.post(
    "/logout",
    status_code=200,
    summary="Revoke refresh token and end session",
)
async def logout(
    payload: LogoutRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.logout(payload)
    return {"message": "Successfully logged out"}


@router.post(
    "/verify-email",
    status_code=200,
    summary="Verify user email address using token",
)
async def verify_email(
    payload: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.verify_email(payload)
    return {"message": "Email verified successfully"}


@router.post(
    "/resend-verification",
    status_code=200,
    dependencies=[Depends(auth_limiter)],
    summary="Request a new email verification token",
)
async def resend_verification(
    payload: ForgotPasswordRequest,  # uses email field
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.resend_verification(payload.email)
    return {
        "message": "If the email is registered and unverified, a verification link has been sent."
    }


@router.post(
    "/forgot-password",
    status_code=200,
    dependencies=[Depends(auth_limiter)],
    summary="Request password reset token",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.forgot_password(payload.email)
    return {"message": "If the email is registered, password reset instructions have been sent."}


@router.post(
    "/reset-password",
    status_code=200,
    dependencies=[Depends(auth_limiter)],
    summary="Reset password with reset token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.reset_password(payload)
    return {
        "message": "Password has been reset successfully. Please log in with your new password."
    }
