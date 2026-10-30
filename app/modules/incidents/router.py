import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_user
from app.modules.incidents.schemas import (
    IncidentClusterResponse,
    IncidentCreate,
    IncidentFlagCreate,
    IncidentFlagResponse,
    IncidentMapItemResponse,
    IncidentPublicDetailResponse,
    IncidentResolveResponse,
    IncidentResubmitRequest,
    IncidentResubmitResponse,
    IncidentStatusResponse,
    IncidentSubmissionResponse,
    MediaConfirmRequest,
    MediaConfirmResponse,
    ReporterIncidentResponse,
)
from app.modules.incidents.service import IncidentService
from app.modules.users.models import User

router = APIRouter(prefix="/incidents", tags=["Incidents"])
me_incidents_router = APIRouter(prefix="/me/incidents", tags=["Me"])

submission_limiter = rate_limit(
    max_requests=settings.RATE_LIMIT_SUBMISSION_PER_HOUR,
    window_seconds=3600,
    key_prefix="incident_submission",
)

flag_limiter = rate_limit(
    max_requests=settings.RATE_LIMIT_FLAG_PER_MINUTE,
    window_seconds=60,
    key_prefix="incident_flags",
)


@router.get(
    "",
    response_model=list[IncidentMapItemResponse] | list[IncidentClusterResponse],
    summary="Query active published incidents on map by center/radius or bounding box",
)
async def query_map_incidents(
    lat: float | None = Query(default=None, description="Center latitude"),
    lon: float | None = Query(default=None, description="Center longitude"),
    radius_km: float | None = Query(default=None, description="Radius in km"),
    min_lat: float | None = Query(default=None),
    min_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    clustered: bool = Query(default=False, description="Return grid-aggregated clusters"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[IncidentMapItemResponse] | list[IncidentClusterResponse]:
    service = IncidentService(db)
    return await service.search_map_incidents(
        center_lat=lat,
        center_lon=lon,
        radius_km=radius_km,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
        category_id=category_id,
        clustered=clustered,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentPublicDetailResponse,
    summary="Get sanitized public incident details with age and relative distance",
)
async def get_incident_public_details(
    incident_id: uuid.UUID,
    lat: float | None = Query(default=None, description="Client latitude for distance calculation"),
    lon: float | None = Query(
        default=None, description="Client longitude for distance calculation"
    ),
    db: AsyncSession = Depends(get_db),
) -> IncidentPublicDetailResponse:
    service = IncidentService(db)
    return await service.get_public_incident_details(
        incident_id=incident_id,
        client_lat=lat,
        client_lon=lon,
    )


@router.post(
    "/{incident_id}/flags",
    response_model=IncidentFlagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Flag an incident report as incorrect, abuse, or community-resolved",
    dependencies=[Depends(flag_limiter)],
)
async def flag_incident(
    incident_id: uuid.UUID,
    payload: IncidentFlagCreate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentFlagResponse:
    service = IncidentService(db)
    return await service.submit_flag(
        incident_id=incident_id,
        user=current_user,
        data=payload,
    )


@router.post(
    "/{incident_id}/resolve",
    response_model=IncidentResolveResponse,
    summary="Mark an incident resolved (by reporter or moderator)",
)
async def resolve_incident(
    incident_id: uuid.UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentResolveResponse:
    service = IncidentService(db)
    return await service.resolve_by_reporter(
        incident_id=incident_id,
        user=current_user,
    )


@router.post(
    "",
    response_model=IncidentSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new incident report and obtain signed Cloudinary upload params",
    dependencies=[Depends(submission_limiter)],
)
async def submit_incident(
    payload: IncidentCreate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentSubmissionResponse:
    service = IncidentService(db)
    return await service.submit_incident(reporter=current_user, data=payload)


@router.post(
    "/{incident_id}/media/confirm",
    response_model=MediaConfirmResponse,
    summary="Confirm uploaded photo with Cloudinary and queue review",
)
async def confirm_incident_media(
    incident_id: uuid.UUID,
    payload: MediaConfirmRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MediaConfirmResponse:
    service = IncidentService(db)
    return await service.confirm_media(
        incident_id=incident_id,
        reporter=current_user,
        data=payload,
    )


@router.get(
    "/{incident_id}/status",
    response_model=IncidentStatusResponse,
    summary="Get current review and lifecycle status of an incident",
)
async def get_incident_status(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> IncidentStatusResponse:
    service = IncidentService(db)
    return await service.get_incident_status(incident_id)


@router.post(
    "/{incident_id}/resubmit",
    response_model=IncidentResubmitResponse,
    summary="Resubmit a rejected report with new metadata or photo",
)
async def resubmit_incident(
    incident_id: uuid.UUID,
    payload: IncidentResubmitRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentResubmitResponse:
    service = IncidentService(db)
    return await service.resubmit_incident(
        incident_id=incident_id,
        reporter=current_user,
        data=payload,
    )


@me_incidents_router.get(
    "",
    response_model=list[ReporterIncidentResponse],
    summary="Get all reports submitted by the current user",
)
async def get_my_incidents(
    review_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReporterIncidentResponse]:
    service = IncidentService(db)
    return await service.list_my_incidents(
        reporter=current_user,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
