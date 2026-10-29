from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings
from app.core.errors import BadRequestError, UnauthorizedError

# Initialize Argon2 hasher with secure defaults
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2 hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_password_strength(password: str) -> None:
    """
    Validate password strength:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < 8:
        raise BadRequestError(
            message="Password must be at least 8 characters long",
            code="weak_password",
        )
    if not any(c.isupper() for c in password):
        raise BadRequestError(
            message="Password must contain at least one uppercase letter",
            code="weak_password",
        )
    if not any(c.islower() for c in password):
        raise BadRequestError(
            message="Password must contain at least one lowercase letter",
            code="weak_password",
        )
    if not any(c.isdigit() for c in password):
        raise BadRequestError(
            message="Password must contain at least one digit",
            code="weak_password",
        )


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)

    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            raise UnauthorizedError(message="Invalid token type", code="invalid_token")
        return payload
    except jwt.ExpiredSignatureError as err:
        raise UnauthorizedError(message="Access token expired", code="token_expired") from err
    except jwt.PyJWTError as err:
        raise UnauthorizedError(message="Invalid or tampered token", code="invalid_token") from err
