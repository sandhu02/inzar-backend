import datetime
import uuid
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job


class JobQueue:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        run_at: datetime.datetime | None = None,
        max_attempts: int = 3,
    ) -> Job:
        now = datetime.datetime.now(UTC)
        job = Job(
            type=job_type,
            payload=payload,
            status="queued",
            run_at=run_at or now,
            attempts=0,
            max_attempts=max_attempts,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def claim_job(self, worker_id: str, lock_timeout_seconds: int = 300) -> Job | None:
        """
        Atomically claim next available job using SELECT ... FOR UPDATE SKIP LOCKED.
        Also reclaims expired running locks.
        """
        now = datetime.datetime.now(UTC)
        lock_threshold = now - timedelta(seconds=lock_timeout_seconds)

        # Claim either ready queued jobs or abandoned running locks
        query = (
            select(Job)
            .where(
                ((Job.status == "queued") & (Job.run_at <= now))
                | ((Job.status == "running") & (Job.locked_at < lock_threshold))
            )
            .order_by(Job.run_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        result = await self.session.execute(query)
        job = result.scalar_one_or_none()

        if job:
            job.status = "running"
            job.locked_at = now
            job.locked_by = worker_id
            job.attempts += 1
            await self.session.flush()

        return job

    async def complete_job(self, job_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="completed",
                locked_at=None,
                locked_by=None,
            )
        )
        await self.session.flush()

    async def fail_job(self, job_id: uuid.UUID, error_message: str) -> None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        now = datetime.datetime.now(UTC)
        job.last_error = error_message[:2000]

        if job.attempts >= job.max_attempts:
            job.status = "dead_letter"
            job.locked_at = None
            job.locked_by = None
        else:
            # Exponential backoff: 5s, 20s, 80s...
            delay_seconds = 5 * (4 ** (job.attempts - 1))
            job.status = "queued"
            job.run_at = now + timedelta(seconds=delay_seconds)
            job.locked_at = None
            job.locked_by = None

        await self.session.flush()
