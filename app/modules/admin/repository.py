import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.jobs.models import Job
from app.modules.admin.models import AuditLog
from app.modules.categories.models import Category
from app.modules.incidents.models import Incident, IncidentFlag
from app.modules.users.models import User


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_audit_log(
        self,
        actor_id: uuid.UUID | None,
        action: str,
        target_type: str,
        target_id: str | None,
        summary: dict[str, Any],
    ) -> AuditLog:
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_audit_logs(
        self,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        query = select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        if actor_id:
            query = query.where(AuditLog.actor_id == actor_id)
        if action:
            query = query.where(AuditLog.action == action)
        if target_type:
            query = query.where(AuditLog.target_type == target_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_moderation_queue(
        self,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        query = (
            select(Incident)
            .where(Incident.review_status == "needs_review")
            .options(selectinload(Incident.media))
            .order_by(Incident.reported_at.asc())
            .offset(offset)
            .limit(limit)
        )
        if category_id:
            query = query.where(Incident.category_id == category_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_flags(
        self,
        flag_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[IncidentFlag, str]]:
        query = (
            select(IncidentFlag, Incident.title)
            .join(Incident, IncidentFlag.incident_id == Incident.id)
            .order_by(IncidentFlag.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if flag_type:
            query = query.where(IncidentFlag.type == flag_type)
        result = await self.session.execute(query)
        return [(row[0], str(row[1])) for row in result.all()]

    async def dismiss_flag(self, flag_id: uuid.UUID) -> bool:
        result = await self.session.execute(delete(IncidentFlag).where(IncidentFlag.id == flag_id))
        await self.session.flush()
        count = int(getattr(result, "rowcount", 0))
        return count > 0

    async def get_users(
        self,
        search_query: str | None = None,
        role: str | None = None,
        is_suspended: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[User, int]]:
        # Count user reports via subquery
        report_subquery = (
            select(Incident.reporter_id, func.count(Incident.id).label("report_count"))
            .group_by(Incident.reporter_id)
            .subquery()
        )

        query = (
            select(User, func.coalesce(report_subquery.c.report_count, 0))
            .outerjoin(report_subquery, User.id == report_subquery.c.reporter_id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        if search_query:
            term = f"%{search_query.lower()}%"
            query = query.where(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.display_name).like(term),
                )
            )
        if role:
            query = query.where(User.role == role)
        if is_suspended is not None:
            query = query.where(User.is_suspended == is_suspended)

        result = await self.session.execute(query)
        return [(row[0], int(row[1])) for row in result.all()]

    async def get_stats_overview(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        week_start = now - timedelta(days=7)

        # Moderation queue count
        q_count = await self.session.execute(
            select(func.count(Incident.id)).where(Incident.review_status == "needs_review")
        )
        moderation_queue_count = q_count.scalar_one() or 0

        # Published count
        pub_count = await self.session.execute(
            select(func.count(Incident.id)).where(
                (Incident.review_status == "published")
                & (Incident.lifecycle_status.in_(["active", "stale"]))
            )
        )
        published_incidents_count = pub_count.scalar_one() or 0

        # Incidents today
        today_c = await self.session.execute(
            select(func.count(Incident.id)).where(Incident.reported_at >= today_start)
        )
        total_incidents_today = today_c.scalar_one() or 0

        # Incidents week
        week_c = await self.session.execute(
            select(func.count(Incident.id)).where(Incident.reported_at >= week_start)
        )
        total_incidents_week = week_c.scalar_one() or 0

        # Total users
        u_c = await self.session.execute(select(func.count(User.id)))
        total_users = u_c.scalar_one() or 0

        # Jobs backlog & dead letter
        j_backlog = await self.session.execute(
            select(func.count(Job.id)).where(Job.status == "queued")
        )
        jobs_backlog = j_backlog.scalar_one() or 0

        j_dead = await self.session.execute(
            select(func.count(Job.id)).where(Job.status == "dead_letter")
        )
        jobs_dead = j_dead.scalar_one() or 0

        # Category distribution
        cat_dist_res = await self.session.execute(
            select(Category.name, func.count(Incident.id))
            .join(Incident, Incident.category_id == Category.id)
            .group_by(Category.name)
        )
        cat_dist = {str(row[0]): int(row[1]) for row in cat_dist_res.all()}

        return {
            "moderation_queue_count": moderation_queue_count,
            "published_incidents_count": published_incidents_count,
            "total_incidents_today": total_incidents_today,
            "total_incidents_week": total_incidents_week,
            "total_users": total_users,
            "jobs_backlog_count": jobs_backlog,
            "jobs_dead_letter_count": jobs_dead,
            "category_distribution": cat_dist,
        }

    async def get_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        query = select(Job).order_by(Job.run_at.desc()).offset(offset).limit(limit)
        if status:
            query = query.where(Job.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def retry_job(self, job_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="queued",
                attempts=0,
                run_at=datetime.now(UTC),
                last_error=None,
                locked_at=None,
                locked_by=None,
            )
        )
        await self.session.flush()
        count = int(getattr(result, "rowcount", 0))
        return count > 0
