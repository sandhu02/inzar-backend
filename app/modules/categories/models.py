from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class Category(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_key: Mapped[str] = mapped_column(String(50), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    urgency: Mapped[str] = mapped_column(String(20), default="routine", nullable=False)
    default_ttl_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    stale_after_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    resolve_flag_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    notify_throttle_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    notify_by_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text, nullable=True)

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
