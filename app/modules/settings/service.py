import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.service import AdminService
from app.modules.settings.models import AppSetting
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schemas import (
    GlobalSettingsSchema,
    GlobalSettingsUpdateSchema,
    PublicConfigResponse,
)

# In-memory settings cache
_cached_settings: GlobalSettingsSchema | None = None
_cached_settings_expiry: float = 0.0
SETTINGS_CACHE_TTL_SECONDS = 60.0


def invalidate_settings_cache() -> None:
    global _cached_settings, _cached_settings_expiry
    _cached_settings = None
    _cached_settings_expiry = 0.0


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SettingsRepository(session)
        self.admin_service = AdminService(session)

    async def seed_defaults_if_needed(self) -> int:
        """Seed default settings into DB if empty."""
        count = await self.repo.count()
        if count > 0:
            return 0

        defaults = GlobalSettingsSchema()
        created = 0
        for key, val in defaults.model_dump().items():
            existing = await self.repo.get(key)
            if not existing:
                await self.repo.set(
                    key=key,
                    value=val,
                    description=f"Global configuration tunable: {key}",
                )
                created += 1

        if created > 0:
            await self.session.commit()
            invalidate_settings_cache()
        return created

    async def get_global_settings(self) -> GlobalSettingsSchema:
        """Retrieve all global settings, using short-lived cache."""
        global _cached_settings, _cached_settings_expiry
        now = time.monotonic()
        if _cached_settings is not None and now < _cached_settings_expiry:
            return _cached_settings

        all_settings = await self.repo.get_all()
        settings_dict = {s.key: s.value for s in all_settings}

        # Build schema using default values for any missing keys
        default_obj = GlobalSettingsSchema()
        merged = default_obj.model_dump()
        for k, v in settings_dict.items():
            if k in merged and v is not None:
                merged[k] = v

        parsed = GlobalSettingsSchema.model_validate(merged)
        _cached_settings = parsed
        _cached_settings_expiry = now + SETTINGS_CACHE_TTL_SECONDS
        return parsed

    async def get_public_config(self) -> PublicConfigResponse:
        """Return public configuration values."""
        settings = await self.get_global_settings()
        return PublicConfigResponse(
            max_search_radius_km=settings.max_search_radius_km,
            allowed_radius_options_km=settings.allowed_radius_options_km,
            max_description_length=settings.max_description_length,
            fuzz_distance_m=settings.fuzz_distance_m,
        )

    async def get_all_raw(self) -> list[AppSetting]:
        return await self.repo.get_all()

    async def update_global_settings(
        self, updates: GlobalSettingsUpdateSchema, actor_id: uuid.UUID | None = None
    ) -> GlobalSettingsSchema:
        """Update global settings with validation, audit logging, and cache invalidation."""
        current = await self.get_global_settings()
        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            return current

        # Validate that merged result is still valid under GlobalSettingsSchema
        merged = current.model_dump()
        merged.update(update_data)
        validated = GlobalSettingsSchema.model_validate(merged)

        before: dict[str, Any] = {}
        after: dict[str, Any] = {}

        for key, value in update_data.items():
            before[key] = getattr(current, key)
            after[key] = value
            await self.repo.set(key=key, value=value, updated_by=actor_id)

        await self.admin_service.log_audit_action(
            action="settings.update",
            target_type="settings",
            target_id="global",
            summary={"before": before, "after": after},
            actor_id=actor_id,
        )

        await self.session.commit()
        invalidate_settings_cache()
        return validated
