import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    RateLimitExceededError,
)
from app.core.geo import fuzz_coordinates, haversine_distance_m, validate_bbox, validate_coordinates
from app.integrations.cloudinary.service import BaseCloudinaryService, get_cloudinary_service
from app.jobs.queue import JobQueue
from app.modules.categories.service import CategoryService
from app.modules.incidents.models import Incident
from app.modules.incidents.repository import IncidentRepository
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
from app.modules.settings.service import SettingsService
from app.modules.users.models import User


class IncidentService:
    def __init__(
        self,
        session: AsyncSession,
        cloudinary_service: BaseCloudinaryService | None = None,
    ) -> None:
        self.session = session
        self.repo = IncidentRepository(session)
        self.category_service = CategoryService(session)
        self.settings_service = SettingsService(session)
        self.cloudinary = cloudinary_service or get_cloudinary_service()
        self.queue = JobQueue(session)

    async def get_incident_by_id(
        self, incident_id: uuid.UUID, include_media: bool = False
    ) -> Incident:
        incident = await self.repo.get_by_id(incident_id, include_media=include_media)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")
        return incident

    async def update_incident_for_moderation(
        self, incident: Incident, updates: dict[str, Any]
    ) -> Incident:
        return await self.repo.update(incident, updates)

    async def submit_incident(
        self,
        reporter: User,
        data: IncidentCreate,
    ) -> IncidentSubmissionResponse:
        # 1. Suspended check
        if reporter.is_suspended:
            raise ForbiddenError(code="account_suspended", message="Account is suspended.")

        # 2. Settings checks
        settings = await self.settings_service.get_global_settings()
        now = datetime.now(UTC)

        if settings.min_account_age_minutes_to_report > 0:
            min_age = timedelta(minutes=settings.min_account_age_minutes_to_report)
            if (now - reporter.created_at) < min_age:
                raise ForbiddenError(
                    code="account_too_new",
                    message="Account is too new to submit incident reports.",
                )

        if len(data.description) > settings.max_description_length:
            raise BadRequestError(
                code="description_too_long",
                message=f"Description exceeds maximum length of {settings.max_description_length} characters.",
            )

        # 3. Rate limiting per user per hour
        recent_count = await self.repo.count_user_reports_since(
            reporter.id, now - timedelta(hours=1)
        )
        if recent_count >= settings.max_reports_per_user_per_hour:
            raise RateLimitExceededError(
                code="report_rate_limit_exceeded",
                message="Report submission limit reached for this hour. Please try again later.",
            )

        # 4. Category validity
        category = await self.category_service.get_category_by_id(data.category_id)
        if not category.is_active:
            raise BadRequestError(
                code="category_inactive",
                message="Selected category is currently inactive.",
            )

        # 5. Coordinate validation & deterministic fuzzing
        validate_coordinates(data.latitude, data.longitude)
        incident_id = uuid.uuid4()
        fuzzed_lat, fuzzed_lon = fuzz_coordinates(
            lat=data.latitude,
            lon=data.longitude,
            seed=str(incident_id),
            fuzz_distance_m=float(settings.fuzz_distance_m),
        )

        # 6. Create incident in DB
        incident = await self.repo.create_incident(
            reporter_id=reporter.id,
            category_id=data.category_id,
            title=data.title,
            description=data.description,
            exact_lat=data.latitude,
            exact_lon=data.longitude,
            fuzzed_lat=fuzzed_lat,
            fuzzed_lon=fuzzed_lon,
            place_label=data.place_label,
        )

        # 7. Generate signed upload parameters for Cloudinary
        upload_params = self.cloudinary.generate_upload_signature(incident.id)

        await self.session.commit()

        return IncidentSubmissionResponse(
            incident_id=incident.id,
            review_status=incident.review_status,
            upload_params=upload_params,
        )

    async def confirm_media(
        self,
        incident_id: uuid.UUID,
        reporter: User,
        data: MediaConfirmRequest,
    ) -> MediaConfirmResponse:
        incident = await self.repo.get_by_id(incident_id, include_media=True)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        # Reporter access check
        if incident.reporter_id != reporter.id and reporter.role not in ["admin", "moderator"]:
            raise ForbiddenError(
                code="forbidden", message="Cannot confirm media for another user's report."
            )

        # Idempotency: if already confirmed
        if incident.review_status in ["checking", "published", "needs_review"]:
            existing_media = incident.media[0] if incident.media else None
            media_id = existing_media.id if existing_media else uuid.uuid4()
            return MediaConfirmResponse(
                incident_id=incident.id,
                review_status=incident.review_status,
                media_id=media_id,
            )

        # Verify asset with Cloudinary
        asset_info = await self.cloudinary.verify_asset(data.cloudinary_public_id)
        if not asset_info:
            raise BadRequestError(
                code="media_verification_failed",
                message="Cloudinary asset could not be verified or does not exist.",
            )

        media = await self.repo.create_media(
            incident_id=incident.id,
            cloudinary_public_id=data.cloudinary_public_id,
            secure_url=asset_info.get("secure_url", data.secure_url),
            width=asset_info.get("width") or data.width,
            height=asset_info.get("height") or data.height,
            bytes_count=asset_info.get("bytes") or data.bytes,
            format_ext=asset_info.get("format") or data.format,
            status="confirmed",
        )

        # Advance to checking and enqueue review job
        await self.repo.update(
            incident,
            {"review_status": "checking"},
        )

        await self.queue.enqueue(
            job_type="review_incident",
            payload={"incident_id": str(incident.id)},
        )

        await self.session.commit()

        return MediaConfirmResponse(
            incident_id=incident.id,
            review_status="checking",
            media_id=media.id,
        )

    async def get_incident_status(self, incident_id: uuid.UUID) -> IncidentStatusResponse:
        incident = await self.repo.get_by_id(incident_id)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        return IncidentStatusResponse(
            id=incident.id,
            review_status=incident.review_status,
            review_reason=incident.review_reason,
            verification_label=incident.verification_label,
            lifecycle_status=incident.lifecycle_status,
            published_at=incident.published_at,
        )

    async def resubmit_incident(
        self,
        incident_id: uuid.UUID,
        reporter: User,
        data: IncidentResubmitRequest,
    ) -> IncidentResubmitResponse:
        incident = await self.repo.get_by_id(incident_id)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        if incident.reporter_id != reporter.id and reporter.role != "admin":
            raise ForbiddenError(code="forbidden", message="Cannot resubmit another user's report.")

        if incident.review_status != "rejected":
            raise BadRequestError(
                code="invalid_state_for_resubmission",
                message="Only rejected incidents can be resubmitted.",
            )

        updates: dict[str, Any] = {
            "review_status": "awaiting_media",
            "review_reason": None,
        }
        if data.title:
            updates["title"] = data.title
        if data.description:
            updates["description"] = data.description

        await self.repo.update(incident, updates)
        upload_params = self.cloudinary.generate_upload_signature(incident.id)

        await self.session.commit()

        return IncidentResubmitResponse(
            incident_id=incident.id,
            review_status="awaiting_media",
            upload_params=upload_params,
        )

    async def list_my_incidents(
        self,
        reporter: User,
        review_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReporterIncidentResponse]:
        incidents = await self.repo.list_by_reporter(
            reporter_id=reporter.id,
            review_status=review_status,
            limit=limit,
            offset=offset,
        )

        results: list[ReporterIncidentResponse] = []
        for inc in incidents:
            media_url = inc.media[0].secure_url if inc.media else None
            results.append(
                ReporterIncidentResponse(
                    id=inc.id,
                    category_id=inc.category_id,
                    title=inc.title,
                    description=inc.description,
                    latitude=inc.public_lat,
                    longitude=inc.public_lon,
                    place_label=inc.place_label,
                    review_status=inc.review_status,
                    review_reason=inc.review_reason,
                    verification_label=inc.verification_label,
                    lifecycle_status=inc.lifecycle_status,
                    reported_at=inc.reported_at,
                    published_at=inc.published_at,
                    media_url=media_url,
                )
            )
        return results

    async def get_public_incident_details(
        self,
        incident_id: uuid.UUID,
        client_lat: float | None = None,
        client_lon: float | None = None,
    ) -> IncidentPublicDetailResponse:
        incident = await self.repo.get_by_id(incident_id, include_media=True)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        # If incident has expired or was removed
        if incident.lifecycle_status == "expired":
            raise GoneError(code="incident_expired", message="This incident has expired.")
        if incident.review_status != "published":
            raise NotFoundError(
                code="incident_not_found", message="Incident not found or unpublished."
            )

        now = datetime.now(UTC)
        age_minutes = max(0, int((now - incident.reported_at).total_seconds() / 60))

        distance_m = None
        if client_lat is not None and client_lon is not None:
            distance_m = round(
                haversine_distance_m(
                    client_lat, client_lon, incident.public_lat, incident.public_lon
                ),
                1,
            )

        media_url = incident.media[0].secure_url if incident.media else None

        return IncidentPublicDetailResponse(
            id=incident.id,
            category_id=incident.category_id,
            title=incident.title,
            description=incident.description,
            latitude=incident.public_lat,
            longitude=incident.public_lon,
            place_label=incident.place_label,
            review_status=incident.review_status,
            verification_label=incident.verification_label,
            lifecycle_status=incident.lifecycle_status,
            reported_at=incident.reported_at,
            published_at=incident.published_at,
            last_confirmed_at=incident.last_confirmed_at,
            resolved_at=incident.resolved_at,
            age_minutes=age_minutes,
            distance_m=distance_m,
            media_url=media_url,
        )

    async def search_map_incidents(
        self,
        center_lat: float | None = None,
        center_lon: float | None = None,
        radius_km: float | None = None,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
        category_id: uuid.UUID | None = None,
        clustered: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IncidentMapItemResponse] | list[IncidentClusterResponse]:
        settings = await self.settings_service.get_global_settings()
        now = datetime.now(UTC)

        # 1. Bounding box query
        if (
            min_lat is not None
            and min_lon is not None
            and max_lat is not None
            and max_lon is not None
        ):
            validate_bbox(min_lat, min_lon, max_lat, max_lon)
            incidents = await self.repo.search_by_bbox(
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
                category_id=category_id,
                limit=limit,
                offset=offset,
            )
            items: list[IncidentMapItemResponse] = []
            for inc in incidents:
                cat = await self.category_service.get_category_by_id(inc.category_id)
                age = max(0, int((now - inc.reported_at).total_seconds() / 60))
                thumb = inc.media[0].secure_url if inc.media else None
                items.append(
                    IncidentMapItemResponse(
                        id=inc.id,
                        category_id=inc.category_id,
                        title=inc.title,
                        latitude=inc.public_lat,
                        longitude=inc.public_lon,
                        place_label=inc.place_label,
                        urgency=cat.urgency,
                        age_minutes=age,
                        distance_m=None,
                        verification_label=inc.verification_label,
                        media_thumbnail_url=thumb,
                    )
                )
            return items

        # 2. Center + Radius query
        if center_lat is None or center_lon is None:
            raise BadRequestError(
                code="missing_query_parameters",
                message="Either (center_lat, center_lon, radius_km) or bounding box parameters are required.",
            )

        validate_coordinates(center_lat, center_lon)
        eff_radius_km = min(radius_km or 10.0, float(settings.max_search_radius_km))
        radius_meters = eff_radius_km * 1000.0

        if clustered:
            clusters_raw = await self.repo.cluster_by_radius(
                center_lat=center_lat,
                center_lon=center_lon,
                radius_meters=radius_meters,
            )
            return [IncidentClusterResponse.model_validate(c) for c in clusters_raw]

        pairs = await self.repo.search_by_radius(
            center_lat=center_lat,
            center_lon=center_lon,
            radius_meters=radius_meters,
            category_id=category_id,
            limit=limit,
            offset=offset,
        )

        map_items: list[IncidentMapItemResponse] = []
        for inc, dist_m in pairs:
            cat = await self.category_service.get_category_by_id(inc.category_id)
            age = max(0, int((now - inc.reported_at).total_seconds() / 60))
            thumb = inc.media[0].secure_url if inc.media else None
            map_items.append(
                IncidentMapItemResponse(
                    id=inc.id,
                    category_id=inc.category_id,
                    title=inc.title,
                    latitude=inc.public_lat,
                    longitude=inc.public_lon,
                    place_label=inc.place_label,
                    urgency=cat.urgency,
                    age_minutes=age,
                    distance_m=round(dist_m, 1),
                    verification_label=inc.verification_label,
                    media_thumbnail_url=thumb,
                )
            )
        return map_items

    async def submit_flag(
        self,
        incident_id: uuid.UUID,
        user: User,
        data: IncidentFlagCreate,
    ) -> IncidentFlagResponse:
        incident = await self.repo.get_by_id(incident_id)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        existing = await self.repo.get_flag(
            incident_id=incident_id,
            user_id=user.id,
            flag_type=data.type,
        )
        if existing:
            raise ConflictError(
                code="flag_already_submitted",
                message=f"You have already submitted a '{data.type}' flag for this incident.",
            )

        flag = await self.repo.create_flag(
            incident_id=incident_id,
            user_id=user.id,
            flag_type=data.type,
            note=data.note,
        )

        settings = await self.settings_service.get_global_settings()
        now = datetime.now(UTC)

        # Abuse/Incorrect flag handling
        if data.type in ["abuse", "incorrect"]:
            count = await self.repo.count_abuse_or_incorrect_flags(incident_id)
            if count >= settings.abuse_flag_hide_threshold:
                await self.repo.update(
                    incident,
                    {
                        "review_status": "needs_review",
                        "review_reason": f"Automatically hidden due to {count} community flags",
                    },
                )

        # Community resolve threshold handling
        elif data.type == "resolved":
            count = await self.repo.count_flags_by_type(incident_id, "resolved")
            category = await self.category_service.get_category_by_id(incident.category_id)
            if count >= category.resolve_flag_threshold:
                await self.repo.update(
                    incident,
                    {
                        "lifecycle_status": "resolved",
                        "resolved_at": now,
                    },
                )

        # Corroboration update
        await self.repo.update(
            incident,
            {
                "last_confirmed_at": now,
                "verification_label": "community_corroborated",
            },
        )

        await self.session.commit()

        return IncidentFlagResponse(
            id=flag.id,
            incident_id=flag.incident_id,
            type=flag.type,
            created_at=flag.created_at,
        )

    async def resolve_by_reporter(
        self,
        incident_id: uuid.UUID,
        user: User,
    ) -> IncidentResolveResponse:
        incident = await self.repo.get_by_id(incident_id)
        if not incident:
            raise NotFoundError(code="incident_not_found", message="Incident not found.")

        if incident.reporter_id != user.id and user.role not in ["admin", "moderator"]:
            raise ForbiddenError(
                code="forbidden", message="Only the reporter or admin can resolve this incident."
            )

        now = datetime.now(UTC)
        await self.repo.update(
            incident,
            {
                "lifecycle_status": "resolved",
                "resolved_at": now,
            },
        )
        await self.session.commit()

        return IncidentResolveResponse(
            incident_id=incident.id,
            lifecycle_status="resolved",
            resolved_at=now,
        )

    async def run_lifecycle_sweep(self) -> int:
        """Mark expired incidents."""
        now = datetime.now(UTC)
        expired = await self.repo.get_expired_incidents(now)
        for inc in expired:
            await self.repo.update(inc, {"lifecycle_status": "expired"})
        if expired:
            await self.session.commit()
        return len(expired)
