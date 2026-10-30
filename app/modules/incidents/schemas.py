import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    title: str = Field(..., min_length=3, max_length=150)
    description: str = Field(..., min_length=5, max_length=5000)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    place_label: str | None = Field(default=None, max_length=200)


class IncidentSubmissionResponse(BaseModel):
    incident_id: uuid.UUID
    review_status: str
    upload_params: dict[str, Any]


class MediaConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloudinary_public_id: str = Field(..., min_length=5, max_length=255)
    secure_url: str = Field(..., min_length=10, max_length=500)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    bytes: int | None = Field(default=None, ge=1)
    format: str | None = Field(default=None, max_length=20)


class MediaConfirmResponse(BaseModel):
    incident_id: uuid.UUID
    review_status: str
    media_id: uuid.UUID


class IncidentStatusResponse(BaseModel):
    id: uuid.UUID
    review_status: str
    review_reason: str | None
    verification_label: str
    lifecycle_status: str
    published_at: datetime | None


class IncidentResubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, min_length=5, max_length=5000)


class IncidentResubmitResponse(BaseModel):
    incident_id: uuid.UUID
    review_status: str
    upload_params: dict[str, Any]


class ReporterIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    description: str
    latitude: float
    longitude: float
    place_label: str | None
    review_status: str
    review_reason: str | None
    verification_label: str
    lifecycle_status: str
    reported_at: datetime
    published_at: datetime | None
    media_url: str | None = None


class IncidentPublicDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    description: str
    latitude: float
    longitude: float
    place_label: str | None
    review_status: str
    verification_label: str
    lifecycle_status: str
    reported_at: datetime
    published_at: datetime | None
    last_confirmed_at: datetime | None
    resolved_at: datetime | None
    age_minutes: int
    distance_m: float | None = None
    media_url: str | None = None


class IncidentMapItemResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    latitude: float
    longitude: float
    place_label: str | None
    urgency: str
    age_minutes: int
    distance_m: float | None = None
    verification_label: str
    media_thumbnail_url: str | None = None


class IncidentClusterResponse(BaseModel):
    cluster_id: str
    latitude: float
    longitude: float
    count: int


class IncidentFlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., pattern=r"^(incorrect|abuse|resolved)$")
    note: str | None = Field(default=None, max_length=500)


class IncidentFlagResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    type: str
    created_at: datetime


class IncidentResolveResponse(BaseModel):
    incident_id: uuid.UUID
    lifecycle_status: str
    resolved_at: datetime
