import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import AppSetting


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> AppSetting | None:
        result = await self.session.execute(select(AppSetting).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[AppSetting]:
        result = await self.session.execute(select(AppSetting))
        return list(result.scalars().all())

    async def set(
        self,
        key: str,
        value: Any,
        description: str | None = None,
        updated_by: uuid.UUID | None = None,
    ) -> AppSetting:
        setting = await self.get(key)
        now = datetime.now(UTC)
        if setting:
            setting.value = value
            if description is not None:
                setting.description = description
            setting.updated_by = updated_by
            setting.updated_at = now
        else:
            setting = AppSetting(
                key=key,
                value=value,
                description=description,
                updated_by=updated_by,
                updated_at=now,
            )
            self.session.add(setting)
        await self.session.flush()
        return setting

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(AppSetting))
        return result.scalar_one() or 0
