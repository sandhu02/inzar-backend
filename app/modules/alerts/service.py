from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import validate_coordinates
from app.modules.alerts.repository import AlertRepository
from app.modules.alerts.schemas import (
    AlertPreferencesResponse,
    AlertPreferencesUpdate,
    DeviceTokenCreate,
    DeviceTokenResponse,
)
from app.modules.users.models import User


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlertRepository(session)

    async def get_preferences(self, user: User) -> AlertPreferencesResponse:
        pref = await self.repo.get_preferences(user.id)
        if not pref:
            # Default preferences: center at (0, 0) disabled until configured
            return AlertPreferencesResponse(
                user_id=user.id,
                enabled=False,
                latitude=0.0,
                longitude=0.0,
                radius_km=5.0,
                categories=[],
                min_urgency="routine",
                updated_at=datetime.now(UTC),
            )
        return AlertPreferencesResponse(
            user_id=pref.user_id,
            enabled=pref.enabled,
            latitude=pref.center_lat,
            longitude=pref.center_lon,
            radius_km=pref.radius_km,
            categories=pref.categories,
            min_urgency=pref.min_urgency,
            updated_at=pref.updated_at,
        )

    async def update_preferences(
        self, user: User, data: AlertPreferencesUpdate
    ) -> AlertPreferencesResponse:
        current = await self.repo.get_preferences(user.id)

        enabled = (
            data.enabled if data.enabled is not None else (current.enabled if current else True)
        )
        lat = (
            data.latitude if data.latitude is not None else (current.center_lat if current else 0.0)
        )
        lon = (
            data.longitude
            if data.longitude is not None
            else (current.center_lon if current else 0.0)
        )
        radius = (
            data.radius_km
            if data.radius_km is not None
            else (current.radius_km if current else 5.0)
        )
        categories = (
            data.categories
            if data.categories is not None
            else (current.categories if current else [])
        )
        min_urgency = (
            data.min_urgency
            if data.min_urgency is not None
            else (current.min_urgency if current else "routine")
        )

        validate_coordinates(lat, lon)

        pref = await self.repo.set_preferences(
            user_id=user.id,
            enabled=enabled,
            center_lat=lat,
            center_lon=lon,
            radius_km=radius,
            categories=categories,
            min_urgency=min_urgency,
        )
        await self.session.commit()

        return AlertPreferencesResponse(
            user_id=pref.user_id,
            enabled=pref.enabled,
            latitude=pref.center_lat,
            longitude=pref.center_lon,
            radius_km=pref.radius_km,
            categories=pref.categories,
            min_urgency=pref.min_urgency,
            updated_at=pref.updated_at,
        )

    async def register_device(self, user: User, data: DeviceTokenCreate) -> DeviceTokenResponse:
        device = await self.repo.register_device_token(
            user_id=user.id,
            token=data.token,
            platform=data.platform,
        )
        await self.session.commit()
        return DeviceTokenResponse(
            id=device.id,
            token=device.token,
            platform=device.platform,
            last_seen_at=device.last_seen_at,
        )

    async def unregister_device(self, user: User, token: str) -> bool:
        success = await self.repo.remove_device_token(user_id=user.id, token=token)
        await self.session.commit()
        return success
