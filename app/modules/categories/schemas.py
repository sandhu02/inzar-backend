import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., pattern=r"^[a-z0-9_]+$", min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    icon_key: str = Field(..., min_length=1, max_length=50)
    color_hex: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True
    urgency: Literal["routine", "high"] = "routine"
    default_ttl_minutes: int = Field(default=1440, ge=1, le=43200)
    stale_after_minutes: int = Field(default=180, ge=1, le=10080)
    resolve_flag_threshold: int = Field(default=3, ge=1, le=50)
    notify_throttle_minutes: int = Field(default=60, ge=0, le=1440)
    notify_by_default: bool = True
    require_manual_review: bool = False
    safety_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_stale_before_ttl(self) -> "CategoryCreate":
        if self.stale_after_minutes > self.default_ttl_minutes:
            raise ValueError("stale_after_minutes cannot be greater than default_ttl_minutes")
        return self


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=100)
    icon_key: str | None = Field(default=None, min_length=1, max_length=50)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    urgency: Literal["routine", "high"] | None = None
    default_ttl_minutes: int | None = Field(default=None, ge=1, le=43200)
    stale_after_minutes: int | None = Field(default=None, ge=1, le=10080)
    resolve_flag_threshold: int | None = Field(default=None, ge=1, le=50)
    notify_throttle_minutes: int | None = Field(default=None, ge=0, le=1440)
    notify_by_default: bool | None = None
    require_manual_review: bool | None = None
    safety_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_stale_before_ttl(self) -> "CategoryUpdate":
        if (
            self.stale_after_minutes is not None
            and self.default_ttl_minutes is not None
            and self.stale_after_minutes > self.default_ttl_minutes
        ):
            raise ValueError("stale_after_minutes cannot be greater than default_ttl_minutes")
        return self


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    icon_key: str
    color_hex: str
    sort_order: int
    is_active: bool
    urgency: str
    default_ttl_minutes: int
    stale_after_minutes: int
    resolve_flag_threshold: int
    notify_throttle_minutes: int
    notify_by_default: bool
    require_manual_review: bool
    safety_note: str | None
    created_at: datetime
    updated_at: datetime


class CategoryPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    icon_key: str
    color_hex: str
    sort_order: int
    urgency: str
    safety_note: str | None
