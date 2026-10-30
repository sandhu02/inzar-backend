import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.admin.schemas import (
    AdminFlagListItemResponse,
    AdminJobItemResponse,
    AdminStatsOverviewResponse,
    AdminUserListItemResponse,
    AdminUserUpdateRequest,
    AuditLogResponse,
    ModerationApproveRequest,
    ModerationIncidentResponse,
    ModerationRejectRequest,
)
from app.modules.admin.service import AdminService
from app.modules.auth.dependencies import require_admin, require_moderator
from app.modules.users.models import User

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


# Moderation Queue
@admin_router.get(
    "/moderation/queue",
    response_model=list[ModerationIncidentResponse],
    summary="List incidents requiring moderator review",
)
async def get_moderation_queue(
    category_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> list[ModerationIncidentResponse]:
    service = AdminService(db)
    return await service.get_moderation_queue(
        category_id=category_id,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/moderation/{incident_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve incident and publish to map",
)
async def approve_incident(
    incident_id: uuid.UUID,
    payload: ModerationApproveRequest = ModerationApproveRequest(),
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AdminService(db)
    await service.approve_incident(
        incident_id=incident_id,
        actor=moderator,
        notes=payload.notes,
    )
    return {"status": "approved", "incident_id": str(incident_id)}


@admin_router.post(
    "/moderation/{incident_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject incident with required explanation",
)
async def reject_incident(
    incident_id: uuid.UUID,
    payload: ModerationRejectRequest,
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AdminService(db)
    await service.reject_incident(
        incident_id=incident_id,
        reason=payload.reason,
        actor=moderator,
    )
    return {"status": "rejected", "incident_id": str(incident_id)}


# Flags Management
@admin_router.get(
    "/flags",
    response_model=list[AdminFlagListItemResponse],
    summary="List community flags on incidents",
)
async def list_incident_flags(
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> list[AdminFlagListItemResponse]:
    service = AdminService(db)
    return await service.list_flags(
        flag_type=type,
        limit=limit,
        offset=offset,
    )


@admin_router.patch(
    "/flags/{flag_id}",
    status_code=status.HTTP_200_OK,
    summary="Dismiss or clear a community flag",
)
async def dismiss_flag(
    flag_id: uuid.UUID,
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AdminService(db)
    await service.dismiss_flag(flag_id=flag_id, actor=moderator)
    return {"status": "dismissed", "flag_id": str(flag_id)}


# User Management
@admin_router.get(
    "/users",
    response_model=list[AdminUserListItemResponse],
    summary="List and search system users",
)
async def list_users(
    query: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_suspended: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserListItemResponse]:
    service = AdminService(db)
    return await service.list_users(
        search_query=query,
        role=role,
        is_suspended=is_suspended,
        limit=limit,
        offset=offset,
    )


@admin_router.patch(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Update user role or suspension status",
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AdminService(db)
    await service.update_user(
        user_id=user_id,
        payload=payload,
        actor=admin,
    )
    return {"status": "updated", "user_id": str(user_id)}


# Overview Stats
@admin_router.get(
    "/stats/overview",
    response_model=AdminStatsOverviewResponse,
    summary="System metrics overview",
)
async def get_stats_overview(
    moderator: User = Depends(require_moderator),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsOverviewResponse:
    service = AdminService(db)
    return await service.get_stats_overview()


# Job Management
@admin_router.get(
    "/jobs",
    response_model=list[AdminJobItemResponse],
    summary="List background jobs and dead letters",
)
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminJobItemResponse]:
    service = AdminService(db)
    return await service.list_jobs(
        status=status,
        limit=limit,
        offset=offset,
    )


@admin_router.post(
    "/jobs/{job_id}/retry",
    status_code=status.HTTP_200_OK,
    summary="Re-queue a failed or dead-lettered job",
)
async def retry_job(
    job_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    service = AdminService(db)
    await service.retry_job(job_id=job_id, actor=admin)
    return {"status": "requeued", "job_id": str(job_id)}


# Audit Log
@admin_router.get(
    "/audit-log",
    response_model=list[AuditLogResponse],
    summary="Inspect security and moderation audit log entries",
)
async def list_audit_logs(
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    service = AdminService(db)
    logs = await service.get_audit_logs(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        limit=limit,
        offset=offset,
    )
    return [AuditLogResponse.model_validate(log) for log in logs]
