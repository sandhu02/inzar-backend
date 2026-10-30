import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.incidents.service import IncidentService

logger = logging.getLogger("jobs.lifecycle")


async def handle_lifecycle_sweep(payload: dict[str, Any], session: AsyncSession) -> None:
    service = IncidentService(session)
    expired_count = await service.run_lifecycle_sweep()
    logger.info(f"Lifecycle sweep completed: {expired_count} incidents transitioned to expired.")
