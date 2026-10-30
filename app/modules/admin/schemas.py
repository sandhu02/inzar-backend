import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str | None
    summary: dict[str, Any]
    created_at: datetime


class ModerationIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    category_slug: str
    category_name: str
    urgency: str
    title: str
    description: str
    place_label: str | None
    review_status: str
    review_reason: str | None
    reported_at: datetime
    media_urls: list[str] = []


class ModerationApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


class ModerationRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class AdminUserListItemResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    is_suspended: bool
    created_at: datetime
    report_count: int


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "moderator", "admin"] | None = None
    is_suspended: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class AdminFlagListItemResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    incident_title: str
    user_id: uuid.UUID
    type: str
    note: str | None
    created_at: datetime


class AdminStatsOverviewResponse(BaseModel):
    moderation_queue_count: int
    published_incidents_count: int
    total_incidents_today: int
    total_incidents_week: int
    total_users: int
    jobs_backlog_count: int
    jobs_dead_letter_count: int
    category_distribution: dict[str, int]


class AdminJobItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    run_at: datetime
    created_at: datetime
