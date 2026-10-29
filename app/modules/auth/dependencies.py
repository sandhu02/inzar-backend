import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.users.models import User
from app.modules.users.service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise UnauthorizedError("Missing authentication token", code="unauthorized")

    payload = decode_access_token(credentials.credentials)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Invalid token payload", code="invalid_token")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as err:
        raise UnauthorizedError("Invalid user identity in token", code="invalid_token") from err

    user_service = UserService(session)
    user = await user_service.repository.get_by_id(user_id, include_deleted=True)
    if not user:
        raise UnauthorizedError("User no longer exists", code="user_not_found")

    if user.deleted_at is not None:
        raise UnauthorizedError("Account has been deleted", code="account_deleted")

    if user.is_suspended:
        raise ForbiddenError("Account has been suspended", code="account_suspended")

    # Store user identity in request state for rate limiting and logging
    request.state.user_id = str(user.id)
    return user


async def require_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure caller is authenticated as a valid active user."""
    return current_user


async def require_moderator(current_user: User = Depends(get_current_user)) -> User:
    """Ensure caller is a moderator or admin."""
    if current_user.role not in ("moderator", "admin"):
        raise ForbiddenError("Moderator access required", code="forbidden")
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure caller is an admin."""
    if current_user.role != "admin":
        raise ForbiddenError("Admin access required", code="forbidden")
    return current_user
