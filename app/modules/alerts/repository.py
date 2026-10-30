import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alerts.models import AlertPreference, DeviceToken, NotificationLog


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_preferences(self, user_id: uuid.UUID) -> AlertPreference | None:
        result = await self.session.execute(
            select(AlertPreference).where(AlertPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_preferences(
        self,
        user_id: uuid.UUID,
        enabled: bool = True,
        center_lat: float = 0.0,
        center_lon: float = 0.0,
        radius_km: float = 5.0,
        categories: list[str] | None = None,
        min_urgency: str = "routine",
    ) -> AlertPreference:
        pref = await self.get_preferences(user_id)
        point = WKTElement(f"POINT({center_lon} {center_lat})", srid=4326)
        now = datetime.now(UTC)

        if pref:
            pref.enabled = enabled
            pref.center = point
            pref.center_lat = center_lat
            pref.center_lon = center_lon
            pref.radius_km = radius_km
            pref.categories = categories or []
            pref.min_urgency = min_urgency
            pref.updated_at = now
        else:
            pref = AlertPreference(
                user_id=user_id,
                enabled=enabled,
                center=point,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_km=radius_km,
                categories=categories or [],
                min_urgency=min_urgency,
                updated_at=now,
            )
            self.session.add(pref)
        await self.session.flush()
        return pref

    async def register_device_token(
        self, user_id: uuid.UUID, token: str, platform: str
    ) -> DeviceToken:
        result = await self.session.execute(select(DeviceToken).where(DeviceToken.token == token))
        existing = result.scalar_one_or_none()
        now = datetime.now(UTC)

        if existing:
            existing.user_id = user_id
            existing.platform = platform
            existing.last_seen_at = now
            await self.session.flush()
            return existing

        dt = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            last_seen_at=now,
        )
        self.session.add(dt)
        await self.session.flush()
        return dt

    async def remove_device_token(self, user_id: uuid.UUID, token: str) -> bool:
        result = await self.session.execute(
            delete(DeviceToken).where(
                (DeviceToken.user_id == user_id) & (DeviceToken.token == token)
            )
        )
        await self.session.flush()
        count = int(getattr(result, "rowcount", 0))
        return count > 0

    async def prune_invalid_tokens(self, invalid_tokens: list[str]) -> None:
        if not invalid_tokens:
            return
        await self.session.execute(delete(DeviceToken).where(DeviceToken.token.in_(invalid_tokens)))
        await self.session.flush()

    async def get_tokens_for_users(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not user_ids:
            return {}
        result = await self.session.execute(
            select(DeviceToken.user_id, DeviceToken.token).where(DeviceToken.user_id.in_(user_ids))
        )
        token_map: dict[uuid.UUID, list[str]] = {uid: [] for uid in user_ids}
        for uid, tok in result.all():
            token_map[uid].append(tok)
        return token_map

    async def find_spatially_matching_preferences(
        self, incident_lat: float, incident_lon: float
    ) -> list[AlertPreference]:
        incident_geom = func.ST_SetSRID(func.ST_MakePoint(incident_lon, incident_lat), 4326)

        query = select(AlertPreference).where(
            (AlertPreference.enabled.is_(True))
            & func.ST_DWithin(
                AlertPreference.center,
                incident_geom,
                AlertPreference.radius_km * 1000.0,
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def is_notified(self, user_id: uuid.UUID, incident_id: uuid.UUID, kind: str) -> bool:
        result = await self.session.execute(
            select(func.count(NotificationLog.id)).where(
                (NotificationLog.user_id == user_id)
                & (NotificationLog.incident_id == incident_id)
                & (NotificationLog.kind == kind)
            )
        )
        return (result.scalar_one() or 0) > 0

    async def get_last_notification_time(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> datetime | None:
        result = await self.session.execute(
            select(func.max(NotificationLog.sent_at)).where(
                (NotificationLog.user_id == user_id) & (NotificationLog.category_id == category_id)
            )
        )
        return result.scalar_one_or_none()

    async def log_notification(
        self,
        user_id: uuid.UUID,
        incident_id: uuid.UUID,
        category_id: uuid.UUID,
        kind: str,
    ) -> NotificationLog:
        log = NotificationLog(
            user_id=user_id,
            incident_id=incident_id,
            category_id=category_id,
            kind=kind,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_users_notified_for_incident(self, incident_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(func.distinct(NotificationLog.user_id)).where(
                NotificationLog.incident_id == incident_id
            )
        )
        return list(result.scalars().all())
