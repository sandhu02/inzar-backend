import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    radius_km: float | None = Field(default=None, ge=0.5, le=100.0)
    categories: list[str] | None = None
    min_urgency: Literal["routine", "high"] | None = None


class AlertPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    enabled: bool
    latitude: float
    longitude: float
    radius_km: float
    categories: list[str]
    min_urgency: str
    updated_at: datetime


class DeviceTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=10, max_length=500)
    platform: Literal["android", "ios", "web"]


class DeviceTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    token: str
    platform: str
    last_seen_at: datetime
