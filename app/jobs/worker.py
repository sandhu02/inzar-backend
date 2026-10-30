"""Worker entrypoint for PostgreSQL SKIP LOCKED background job queue."""

import asyncio
import logging
import os
import signal
import socket
from typing import Any

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal
from app.jobs.handlers.fanout_alerts import handle_fanout_alerts
from app.jobs.handlers.lifecycle import handle_lifecycle_sweep
from app.jobs.handlers.review_incident import handle_review_incident
from app.jobs.queue import JobQueue

logger = logging.getLogger("worker")


class Worker:
    def __init__(self, poll_interval_seconds: float = 1.0) -> None:
        self.poll_interval = poll_interval_seconds
        self.running = True
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self._handlers = {
            "review_incident": handle_review_incident,
            "lifecycle_sweep": handle_lifecycle_sweep,
            "fanout_alerts": handle_fanout_alerts,
        }

    def register_handler(self, job_type: str, handler: Any) -> None:
        self._handlers[job_type] = handler

    def stop(self) -> None:
        logger.info(f"Stopping worker {self.worker_id} gracefully...")
        self.running = False

    async def run(self) -> None:
        logger.info(f"Starting background worker {self.worker_id}...")

        while self.running:
            try:
                processed = await self._process_next_job()
                if not processed and self.running:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Unexpected worker loop error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

        logger.info(f"Worker {self.worker_id} shut down.")

    async def _process_next_job(self) -> bool:
        async with AsyncSessionLocal() as session:
            queue = JobQueue(session)
            job = await queue.claim_job(worker_id=self.worker_id)
            if not job:
                return False

            logger.info(
                f"Claimed job {job.id} of type '{job.type}' (attempt {job.attempts}/{job.max_attempts})"
            )
            await session.commit()

            handler = self._handlers.get(job.type)
            if not handler:
                logger.error(f"No handler registered for job type '{job.type}'")
                await queue.fail_job(job.id, f"No handler registered for job type '{job.type}'")
                await session.commit()
                return True

            try:
                await handler(job.payload, session)
                await queue.complete_job(job.id)
                await session.commit()
                logger.info(f"Job {job.id} completed successfully.")
            except Exception as e:
                logger.error(f"Job {job.id} failed with error: {e}")
                await session.rollback()
                await queue.fail_job(job.id, str(e))
                await session.commit()

            return True


def run_worker() -> None:
    setup_logging(settings.LOG_LEVEL)
    worker = Worker()

    def handle_stop(*_: Any) -> None:
        worker.stop()

    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_stop)
            except (NotImplementedError, AttributeError):
                signal.signal(sig, lambda s, f: worker.stop())
    except Exception:
        pass

    asyncio.run(worker.run())


if __name__ == "__main__":
    run_worker()
