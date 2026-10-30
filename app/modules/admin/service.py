import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.integrations.cloudinary.service import BaseCloudinaryService, get_cloudinary_service
from app.jobs.queue import JobQueue
from app.modules.admin.models import AuditLog
from app.modules.admin.repository import AdminRepository
from app.modules.admin.schemas import (
    AdminFlagListItemResponse,
    AdminJobItemResponse,
    AdminStatsOverviewResponse,
    AdminUserListItemResponse,
    AdminUserUpdateRequest,
    ModerationIncidentResponse,
)
from app.modules.categories.service import CategoryService
from app.modules.incidents.service import IncidentService
from app.modules.users.models import User
from app.modules.users.service import UserService


class AdminService:
    def __init__(
        self,
        session: AsyncSession,
        cloudinary_service: BaseCloudinaryService | None = None,
    ) -> None:
        self.session = session
        self.repo = AdminRepository(session)
        self.incident_service = IncidentService(session, cloudinary_service=cloudinary_service)
        self.category_service = CategoryService(session)
        self.user_service = UserService(session)
        self.queue = JobQueue(session)
        self.cloudinary = cloudinary_service or get_cloudinary_service()

    async def log_audit_action(
        self,
        action: str,
        target_type: str,
        target_id: str | None = None,
        summary: dict[str, Any] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> AuditLog:
        return await self.repo.create_audit_log(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary or {},
        )

    async def get_audit_logs(
        self,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        return await self.repo.list_audit_logs(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            limit=limit,
            offset=offset,
        )

    async def get_moderation_queue(
        self,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModerationIncidentResponse]:
        incidents = await self.repo.get_moderation_queue(
            category_id=category_id,
            limit=limit,
            offset=offset,
        )

        results: list[ModerationIncidentResponse] = []
        for inc in incidents:
            cat = await self.category_service.get_category_by_id(inc.category_id)
            cat_name = cat.name if cat else "Unknown"
            cat_slug = cat.slug if cat else "unknown"
            cat_urgency = cat.urgency if cat else "routine"
            media_urls = [m.secure_url for m in inc.media] if inc.media else []

            results.append(
                ModerationIncidentResponse(
                    id=inc.id,
                    category_id=inc.category_id,
                    category_slug=cat_slug,
                    category_name=cat_name,
                    urgency=cat_urgency,
                    title=inc.title,
                    description=inc.description,
                    place_label=inc.place_label,
                    review_status=inc.review_status,
                    review_reason=inc.review_reason,
                    reported_at=inc.reported_at,
                    media_urls=media_urls,
                )
            )
        return results

    async def approve_incident(
        self,
        incident_id: uuid.UUID,
        actor: User,
        notes: str | None = None,
    ) -> None:
        incident = await self.incident_service.get_incident_by_id(incident_id)

        category = await self.category_service.get_category_by_id(incident.category_id)
        ttl = category.default_ttl_minutes if category else 1440

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl)

        before_status = incident.review_status
        await self.incident_service.update_incident_for_moderation(
            incident,
            {
                "review_status": "published",
                "review_reason": notes or "Approved by moderator",
                "published_at": now,
                "expires_at": expires_at,
            },
        )

        # Enqueue fanout alerts
        await self.queue.enqueue(
            job_type="fanout_alerts",
            payload={"incident_id": str(incident.id)},
        )

        # Audit log
        await self.log_audit_action(
            action="incident.approve",
            target_type="incident",
            target_id=str(incident.id),
            summary={"before": before_status, "after": "published", "notes": notes},
            actor_id=actor.id,
        )

        await self.session.commit()

    async def reject_incident(
        self,
        incident_id: uuid.UUID,
        reason: str,
        actor: User,
    ) -> None:
        incident = await self.incident_service.get_incident_by_id(incident_id, include_media=True)

        before_status = incident.review_status
        await self.incident_service.update_incident_for_moderation(
            incident,
            {
                "review_status": "rejected",
                "review_reason": reason,
            },
        )

        # Cleanup media from Cloudinary
        if incident.media:
            for m in incident.media:
                await self.cloudinary.delete_asset(m.cloudinary_public_id)

        # Audit log
        await self.log_audit_action(
            action="incident.reject",
            target_type="incident",
            target_id=str(incident.id),
            summary={"before": before_status, "after": "rejected", "reason": reason},
            actor_id=actor.id,
        )

        await self.session.commit()

    async def list_flags(
        self,
        flag_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminFlagListItemResponse]:
        flags = await self.repo.get_flags(flag_type=flag_type, limit=limit, offset=offset)
        return [
            AdminFlagListItemResponse(
                id=flag.id,
                incident_id=flag.incident_id,
                incident_title=title,
                user_id=flag.user_id,
                type=flag.type,
                note=flag.note,
                created_at=flag.created_at,
            )
            for flag, title in flags
        ]

    async def dismiss_flag(self, flag_id: uuid.UUID, actor: User) -> None:
        success = await self.repo.dismiss_flag(flag_id)
        if not success:
            raise NotFoundError(code="flag_not_found", message="Flag not found.")

        await self.log_audit_action(
            action="flag.dismiss",
            target_type="incident_flag",
            target_id=str(flag_id),
            actor_id=actor.id,
        )
        await self.session.commit()

    async def list_users(
        self,
        search_query: str | None = None,
        role: str | None = None,
        is_suspended: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminUserListItemResponse]:
        results = await self.repo.get_users(
            search_query=search_query,
            role=role,
            is_suspended=is_suspended,
            limit=limit,
            offset=offset,
        )
        return [
            AdminUserListItemResponse(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
                is_suspended=user.is_suspended,
                created_at=user.created_at,
                report_count=count,
            )
            for user, count in results
        ]

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: AdminUserUpdateRequest,
        actor: User,
    ) -> None:
        before, after = await self.user_service.admin_update_user(
            user_id=user_id,
            role=payload.role,
            is_suspended=payload.is_suspended,
        )

        await self.log_audit_action(
            action="user.update",
            target_type="user",
            target_id=str(user_id),
            summary={"before": before, "after": after, "reason": payload.reason},
            actor_id=actor.id,
        )

        await self.session.commit()

    async def get_stats_overview(self) -> AdminStatsOverviewResponse:
        data = await self.repo.get_stats_overview()
        return AdminStatsOverviewResponse.model_validate(data)

    async def list_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminJobItemResponse]:
        jobs = await self.repo.get_jobs(status=status, limit=limit, offset=offset)
        return [AdminJobItemResponse.model_validate(j) for j in jobs]

    async def retry_job(self, job_id: uuid.UUID, actor: User) -> None:
        success = await self.repo.retry_job(job_id)
        if not success:
            raise NotFoundError(code="job_not_found", message="Job not found.")

        await self.log_audit_action(
            action="job.retry",
            target_type="job",
            target_id=str(job_id),
            actor_id=actor.id,
        )
        await self.session.commit()
