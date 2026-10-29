import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.integrations.email.provider import BaseEmailProvider
from app.integrations.google_auth.verifier import BaseGoogleAuthVerifier
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.users.models import User
from app.modules.users.service import UserService

logger = logging.getLogger("inzar.auth")


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        email_provider: BaseEmailProvider,
        google_verifier: BaseGoogleAuthVerifier,
    ) -> None:
        self.session = session
        self.auth_repo = AuthRepository(session)
        self.user_service = UserService(session)
        self.email_provider = email_provider
        self.google_verifier = google_verifier

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _issue_token_pair(
        self,
        user: User,
        user_agent: str | None = None,
        family_id: uuid.UUID | None = None,
    ) -> tuple[str, str, int]:
        """Issue access token and a hashed rotating refresh token."""
        access_token = create_access_token(user_id=str(user.id), role=user.role)

        raw_refresh_token = secrets.token_urlsafe(48)
        refresh_hash = self._hash_token(raw_refresh_token)
        refresh_family = family_id or uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

        await self.auth_repo.create_refresh_token(
            user_id=user.id,
            token_hash=refresh_hash,
            family_id=refresh_family,
            expires_at=expires_at,
            user_agent=user_agent,
        )

        expires_in = settings.ACCESS_TOKEN_TTL_MINUTES * 60
        return access_token, raw_refresh_token, expires_in

    async def signup(self, data: SignupRequest, user_agent: str | None = None) -> TokenResponse:
        # Check duplicate email
        existing = await self.user_service.get_by_email(data.email)
        if existing:
            raise ConflictError("User with this email already exists", code="user_exists")

        validate_password_strength(data.password)
        hashed_pwd = hash_password(data.password)

        user = await self.user_service.create_user(
            email=data.email,
            password_hash=hashed_pwd,
            display_name=data.display_name,
            role="user",
        )

        # Generate and store email verification token
        raw_verify_token = secrets.token_urlsafe(32)
        verify_hash = self._hash_token(raw_verify_token)
        verify_expiry = datetime.now(UTC) + timedelta(hours=settings.EMAIL_TOKEN_TTL_HOURS)

        await self.auth_repo.create_email_token(
            user_id=user.id,
            purpose="verify",
            token_hash=verify_hash,
            expires_at=verify_expiry,
        )

        # Send email in background / via provider
        await self.email_provider.send_verification_email(user.email, raw_verify_token)

        access_token, refresh_token, expires_in = await self._issue_token_pair(user, user_agent)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=self.user_service._to_response(user),
        )

    async def login(self, data: LoginRequest, user_agent: str | None = None) -> TokenResponse:
        user = await self.user_service.get_by_email(data.email)
        # Prevent user enumeration: identical response if user doesn't exist or password mismatch
        if (
            not user
            or not user.password_hash
            or not verify_password(data.password, user.password_hash)
        ):
            raise UnauthorizedError("Invalid email or password", code="invalid_credentials")

        if user.is_suspended:
            raise ForbiddenError("Your account has been suspended", code="account_suspended")

        access_token, refresh_token, expires_in = await self._issue_token_pair(user, user_agent)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=self.user_service._to_response(user),
        )

    async def google_login(
        self, data: GoogleLoginRequest, user_agent: str | None = None
    ) -> TokenResponse:
        claims = await self.google_verifier.verify_id_token(data.id_token)
        google_sub = claims.get("sub")
        email = claims.get("email")
        email_verified = claims.get("email_verified", False)
        display_name = claims.get("name")

        if not google_sub or not email:
            raise UnauthorizedError("Invalid Google ID token claims", code="invalid_google_token")

        if not email_verified:
            raise BadRequestError("Google email is not verified", code="unverified_google_email")

        # 1. Match by google_sub
        user = await self.user_service.get_by_google_sub(google_sub)

        # 2. Match by email if not found
        if not user:
            user = await self.user_service.get_by_email(email)
            if user:
                # Link google_sub
                await self.user_service.repository.update(
                    user,
                    google_sub=google_sub,
                    email_verified_at=user.email_verified_at or datetime.now(UTC),
                )
            else:
                # Create new user
                user = await self.user_service.create_user(
                    email=email,
                    display_name=display_name,
                    google_sub=google_sub,
                    email_verified_at=datetime.now(UTC),
                    role="user",
                )

        if user.is_suspended:
            raise ForbiddenError("Your account has been suspended", code="account_suspended")

        access_token, refresh_token, expires_in = await self._issue_token_pair(user, user_agent)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=self.user_service._to_response(user),
        )

    async def refresh_tokens(
        self, data: RefreshTokenRequest, user_agent: str | None = None
    ) -> TokenResponse:
        token_hash = self._hash_token(data.refresh_token)
        token = await self.auth_repo.get_refresh_token_by_hash(token_hash)

        if not token:
            raise UnauthorizedError("Invalid refresh token", code="invalid_token")

        now = datetime.now(UTC)

        # Reuse detection: If token was already revoked, someone is reusing an old token!
        if token.revoked_at is not None:
            logger.warning(
                f"Refresh token reuse detected for user {token.user_id}, family {token.family_id}. Revoking entire family."
            )
            await self.auth_repo.revoke_refresh_token_family(token.family_id)
            await self.session.commit()
            raise UnauthorizedError(
                "Compromised refresh token detected. All sessions in this chain have been revoked.",
                code="token_compromised",
            )

        if token.expires_at < now:
            raise UnauthorizedError("Refresh token expired", code="token_expired")

        user = await self.user_service.get_user_by_id(token.user_id)
        if user.is_suspended:
            raise ForbiddenError("Your account has been suspended", code="account_suspended")

        # Generate new token in the same family
        raw_refresh_token = secrets.token_urlsafe(48)
        new_refresh_hash = self._hash_token(raw_refresh_token)
        new_expiry = now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

        new_token = await self.auth_repo.create_refresh_token(
            user_id=user.id,
            token_hash=new_refresh_hash,
            family_id=token.family_id,
            expires_at=new_expiry,
            user_agent=user_agent,
        )

        # Revoke the used token and mark replaced_by
        await self.auth_repo.revoke_refresh_token(token, replaced_by=new_token.id)

        access_token = create_access_token(user_id=str(user.id), role=user.role)
        expires_in = settings.ACCESS_TOKEN_TTL_MINUTES * 60

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=self.user_service._to_response(user),
        )

    async def logout(self, data: LogoutRequest) -> None:
        token_hash = self._hash_token(data.refresh_token)
        token = await self.auth_repo.get_refresh_token_by_hash(token_hash)
        if token and token.revoked_at is None:
            await self.auth_repo.revoke_refresh_token(token)

    async def verify_email(self, data: VerifyEmailRequest) -> None:
        token_hash = self._hash_token(data.token)
        token = await self.auth_repo.get_email_token_by_hash(token_hash, purpose="verify")
        if not token or token.used_at is not None or token.expires_at < datetime.now(UTC):
            raise BadRequestError("Invalid or expired verification token", code="invalid_token")

        await self.auth_repo.mark_email_token_used(token)
        await self.user_service.set_email_verified(token.user_id)

    async def resend_verification(self, email: str) -> None:
        user = await self.user_service.get_by_email(email)
        if user and not user.email_verified_at:
            raw_token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(raw_token)
            expiry = datetime.now(UTC) + timedelta(hours=settings.EMAIL_TOKEN_TTL_HOURS)

            await self.auth_repo.create_email_token(
                user_id=user.id,
                purpose="verify",
                token_hash=token_hash,
                expires_at=expiry,
            )
            await self.email_provider.send_verification_email(user.email, raw_token)

    async def forgot_password(self, email: str) -> None:
        user = await self.user_service.get_by_email(email)
        if user and user.password_hash and not user.is_suspended:
            raw_token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(raw_token)
            expiry = datetime.now(UTC) + timedelta(hours=settings.EMAIL_TOKEN_TTL_HOURS)

            await self.auth_repo.create_email_token(
                user_id=user.id,
                purpose="reset",
                token_hash=token_hash,
                expires_at=expiry,
            )
            await self.email_provider.send_password_reset_email(user.email, raw_token)

    async def reset_password(self, data: ResetPasswordRequest) -> None:
        token_hash = self._hash_token(data.token)
        token = await self.auth_repo.get_email_token_by_hash(token_hash, purpose="reset")
        if not token or token.used_at is not None or token.expires_at < datetime.now(UTC):
            raise BadRequestError("Invalid or expired password reset token", code="invalid_token")

        validate_password_strength(data.new_password)
        hashed_pwd = hash_password(data.new_password)

        await self.user_service.update_password(token.user_id, hashed_pwd)
        await self.auth_repo.mark_email_token_used(token)
        # Revoke all active sessions on password change
        await self.auth_repo.revoke_all_user_refresh_tokens(token.user_id)
