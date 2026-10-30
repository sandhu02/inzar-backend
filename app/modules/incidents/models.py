import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class Incident(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incidents"

    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # PostGIS spatial columns (SRID 4326: WGS84)
    location_exact: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=False,
    )
    location_public: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    # Cached fuzzed public coordinates for rapid serialization
    public_lat: Mapped[float] = mapped_column(Float, nullable=False)
    public_lon: Mapped[float] = mapped_column(Float, nullable=False)

    place_label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Status Model
    # awaiting_media -> checking -> published | needs_review | rejected | review_unavailable
    review_status: Mapped[str] = mapped_column(
        String(30), default="awaiting_media", nullable=False, index=True
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # none | ai_reviewed | community_corroborated
    verification_label: Mapped[str] = mapped_column(String(30), default="none", nullable=False)
    # active -> stale -> expired | resolved
    lifecycle_status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False, index=True
    )

    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    media: Mapped[list["IncidentMedia"]] = relationship(
        "IncidentMedia",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentMedia.created_at.desc()",
    )


class IncidentMedia(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_media"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cloudinary_public_id: Mapped[str] = mapped_column(String(255), nullable=False)
    secure_url: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, confirmed, failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship("Incident", back_populates="media")


class IncidentFlag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "incident_flags"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # incorrect | abuse | resolved
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
