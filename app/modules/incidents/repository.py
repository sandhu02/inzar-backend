import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.incidents.models import Incident, IncidentFlag, IncidentMedia


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_incident(
        self,
        reporter_id: uuid.UUID | None,
        category_id: uuid.UUID,
        title: str,
        description: str,
        exact_lat: float,
        exact_lon: float,
        fuzzed_lat: float,
        fuzzed_lon: float,
        place_label: str | None = None,
    ) -> Incident:
        exact_point = WKTElement(f"POINT({exact_lon} {exact_lat})", srid=4326)
        public_point = WKTElement(f"POINT({fuzzed_lon} {fuzzed_lat})", srid=4326)

        incident = Incident(
            reporter_id=reporter_id,
            category_id=category_id,
            title=title,
            description=description,
            location_exact=exact_point,
            location_public=public_point,
            public_lat=fuzzed_lat,
            public_lon=fuzzed_lon,
            place_label=place_label,
            review_status="awaiting_media",
            verification_label="none",
            lifecycle_status="active",
        )
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def get_by_id(
        self, incident_id: uuid.UUID, include_media: bool = False
    ) -> Incident | None:
        query = select(Incident).where(Incident.id == incident_id)
        if include_media:
            query = query.options(selectinload(Incident.media))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update(self, incident: Incident, updates: dict[str, Any]) -> Incident:
        for key, val in updates.items():
            if hasattr(incident, key):
                setattr(incident, key, val)
        incident.updated_at = datetime.now(UTC)
        await self.session.flush()
        return incident

    async def create_media(
        self,
        incident_id: uuid.UUID,
        cloudinary_public_id: str,
        secure_url: str,
        width: int | None = None,
        height: int | None = None,
        bytes_count: int | None = None,
        format_ext: str | None = None,
        status: str = "confirmed",
    ) -> IncidentMedia:
        media = IncidentMedia(
            incident_id=incident_id,
            cloudinary_public_id=cloudinary_public_id,
            secure_url=secure_url,
            width=width,
            height=height,
            bytes=bytes_count,
            format=format_ext,
            status=status,
        )
        self.session.add(media)
        await self.session.flush()
        return media

    async def count_user_reports_since(self, user_id: uuid.UUID, since: datetime) -> int:
        query = (
            select(func.count())
            .select_from(Incident)
            .where((Incident.reporter_id == user_id) & (Incident.reported_at >= since))
        )
        result = await self.session.execute(query)
        return result.scalar_one() or 0

    async def list_by_reporter(
        self,
        reporter_id: uuid.UUID,
        review_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        query = (
            select(Incident)
            .where(Incident.reporter_id == reporter_id)
            .options(selectinload(Incident.media))
            .order_by(Incident.reported_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if review_status:
            query = query.where(Incident.review_status == review_status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search_by_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_meters: float,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[Incident, float]]:
        """Query published incidents within radius using PostGIS ST_DWithin and GiST index."""
        center_geom = func.ST_SetSRID(func.ST_MakePoint(center_lon, center_lat), 4326)
        distance_expr = func.ST_Distance(Incident.location_public, center_geom).label("distance_m")

        query = (
            select(Incident, distance_expr)
            .where(
                (Incident.review_status == "published")
                & (Incident.lifecycle_status.in_(["active", "stale"]))
                & ((Incident.expires_at.is_(None)) | (Incident.expires_at > func.now()))
                & func.ST_DWithin(Incident.location_public, center_geom, radius_meters)
            )
            .options(selectinload(Incident.media))
            .order_by(distance_expr.asc())
            .offset(offset)
            .limit(limit)
        )

        if category_id:
            query = query.where(Incident.category_id == category_id)

        result = await self.session.execute(query)
        return [(row[0], float(row[1])) for row in result.all()]

    async def search_by_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        """Query published incidents within bounding box."""
        query = (
            select(Incident)
            .where(
                (Incident.review_status == "published")
                & (Incident.lifecycle_status.in_(["active", "stale"]))
                & ((Incident.expires_at.is_(None)) | (Incident.expires_at > func.now()))
                & (Incident.public_lat >= min_lat)
                & (Incident.public_lat <= max_lat)
                & (Incident.public_lon >= min_lon)
                & (Incident.public_lon <= max_lon)
            )
            .options(selectinload(Incident.media))
            .order_by(Incident.published_at.desc())
            .offset(offset)
            .limit(limit)
        )

        if category_id:
            query = query.where(Incident.category_id == category_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def cluster_by_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_meters: float,
        grid_size_deg: float = 0.05,
    ) -> list[dict[str, Any]]:
        """Cluster incidents on a spatial grid for low-zoom views."""
        center_geom = func.ST_SetSRID(func.ST_MakePoint(center_lon, center_lat), 4326)

        grid_lat = (
            func.round(func.cast(Incident.public_lat / grid_size_deg, Numeric), 0) * grid_size_deg
        )
        grid_lon = (
            func.round(func.cast(Incident.public_lon / grid_size_deg, Numeric), 0) * grid_size_deg
        )

        query = (
            select(
                grid_lat.label("lat"),
                grid_lon.label("lon"),
                func.count(Incident.id).label("count"),
            )
            .where(
                (Incident.review_status == "published")
                & (Incident.lifecycle_status.in_(["active", "stale"]))
                & func.ST_DWithin(Incident.location_public, center_geom, radius_meters)
            )
            .group_by(grid_lat, grid_lon)
        )

        result = await self.session.execute(query)
        clusters = []
        for row in result.all():
            clusters.append(
                {
                    "cluster_id": f"{row[0]}_{row[1]}",
                    "latitude": float(row[0]),
                    "longitude": float(row[1]),
                    "count": int(row[2]),
                }
            )
        return clusters

    async def create_flag(
        self,
        incident_id: uuid.UUID,
        user_id: uuid.UUID,
        flag_type: str,
        note: str | None = None,
    ) -> IncidentFlag:
        flag = IncidentFlag(
            incident_id=incident_id,
            user_id=user_id,
            type=flag_type,
            note=note,
        )
        self.session.add(flag)
        await self.session.flush()
        return flag

    async def get_flag(
        self, incident_id: uuid.UUID, user_id: uuid.UUID, flag_type: str
    ) -> IncidentFlag | None:
        result = await self.session.execute(
            select(IncidentFlag).where(
                (IncidentFlag.incident_id == incident_id)
                & (IncidentFlag.user_id == user_id)
                & (IncidentFlag.type == flag_type)
            )
        )
        return result.scalar_one_or_none()

    async def count_flags_by_type(self, incident_id: uuid.UUID, flag_type: str) -> int:
        result = await self.session.execute(
            select(func.count(IncidentFlag.id)).where(
                (IncidentFlag.incident_id == incident_id) & (IncidentFlag.type == flag_type)
            )
        )
        return result.scalar_one() or 0

    async def count_abuse_or_incorrect_flags(self, incident_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(IncidentFlag.user_id))).where(
                (IncidentFlag.incident_id == incident_id)
                & (IncidentFlag.type.in_(["abuse", "incorrect"]))
            )
        )
        return result.scalar_one() or 0

    async def get_expired_incidents(self, now: datetime) -> list[Incident]:
        result = await self.session.execute(
            select(Incident).where(
                (Incident.review_status == "published")
                & (Incident.lifecycle_status.in_(["active", "stale"]))
                & (Incident.expires_at <= now)
            )
        )
        return list(result.scalars().all())
