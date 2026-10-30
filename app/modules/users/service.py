import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserExportData, UserResponse, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = UserRepository(session)

    def _to_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        )

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found", code="user_not_found")
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self.repository.get_by_email(email)

    async def get_by_google_sub(self, google_sub: str) -> User | None:
        return await self.repository.get_by_google_sub(google_sub)

    async def create_user(
        self,
        email: str,
        password_hash: str | None = None,
        display_name: str | None = None,
        role: str = "user",
        google_sub: str | None = None,
        email_verified_at: datetime | None = None,
    ) -> User:
        return await self.repository.create(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            google_sub=google_sub,
            email_verified_at=email_verified_at,
        )

    async def set_email_verified(self, user_id: uuid.UUID) -> None:
        user = await self.get_user_by_id(user_id)
        await self.repository.update(user, email_verified_at=datetime.now(UTC))

    async def update_password(self, user_id: uuid.UUID, password_hash: str) -> None:
        user = await self.get_user_by_id(user_id)
        await self.repository.update(user, password_hash=password_hash)

    async def get_profile(self, user_id: uuid.UUID) -> UserResponse:
        user = await self.get_user_by_id(user_id)
        return self._to_response(user)

    async def update_profile(self, user_id: uuid.UUID, data: UserUpdate) -> UserResponse:
        user = await self.get_user_by_id(user_id)
        updated = await self.repository.update(user, display_name=data.display_name)
        return self._to_response(updated)

    async def delete_account(self, user_id: uuid.UUID) -> None:
        user = await self.get_user_by_id(user_id)
        await self.repository.soft_delete(user)

    async def export_data(self, user_id: uuid.UUID) -> UserExportData:
        user = await self.get_user_by_id(user_id)
        return UserExportData(
            user=self._to_response(user),
            export_generated_at=datetime.now(UTC),
        )

    async def admin_update_user(
        self,
        user_id: uuid.UUID,
        role: str | None = None,
        is_suspended: bool | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        user = await self.get_user_by_id(user_id)
        before = {"role": user.role, "is_suspended": user.is_suspended}
        updates: dict[str, Any] = {}
        if role is not None:
            updates["role"] = role
        if is_suspended is not None:
            updates["is_suspended"] = is_suspended
        if updates:
            await self.repository.update(user, **updates)
        after = {"role": user.role, "is_suspended": user.is_suspended}
        return before, after
