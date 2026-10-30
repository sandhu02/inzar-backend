import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.review.provider import BaseReviewProvider, get_review_provider
from app.jobs.queue import JobQueue
from app.modules.categories.repository import CategoryRepository
from app.modules.incidents.repository import IncidentRepository
from app.modules.settings.service import SettingsService

logger = logging.getLogger("jobs.review_incident")


async def handle_review_incident(
    payload: dict[str, Any],
    session: AsyncSession,
    review_provider: BaseReviewProvider | None = None,
) -> None:
    incident_id_str = payload.get("incident_id")
    if not incident_id_str:
        logger.error("Missing incident_id in review job payload")
        return

    incident_id = uuid.UUID(incident_id_str)
    incident_repo = IncidentRepository(session)
    category_repo = CategoryRepository(session)
    settings_service = SettingsService(session)
    queue = JobQueue(session)

    incident = await incident_repo.get_by_id(incident_id)
    if not incident:
        logger.warning(f"Incident {incident_id} not found for review")
        return

    category = await category_repo.get_by_id(incident.category_id)
    if not category:
        logger.error(f"Category {incident.category_id} not found for incident {incident_id}")
        return

    global_settings = await settings_service.get_global_settings()
    provider = review_provider or get_review_provider()

    incident_data = {
        "id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "category_slug": category.slug,
    }
    category_data = {
        "slug": category.slug,
        "require_manual_review": category.require_manual_review,
        "urgency": category.urgency,
    }

    try:
        decision = await provider.review(
            incident_data=incident_data,
            category_data=category_data,
            review_mode=global_settings.review_mode,
        )
    except Exception as e:
        logger.error(f"Review provider error for incident {incident_id}: {e}")
        # Transition to review_unavailable
        await incident_repo.update(
            incident,
            {
                "review_status": "review_unavailable",
                "review_reason": f"Automatic review failed: {str(e)}",
            },
        )
        raise e

    now = datetime.now(UTC)

    if decision.decision == "approved":
        expires_at = now + timedelta(minutes=category.default_ttl_minutes)
        await incident_repo.update(
            incident,
            {
                "review_status": "published",
                "review_reason": decision.reason,
                "published_at": now,
                "expires_at": expires_at,
            },
        )
        # Enqueue alert fanout for published incidents
        await queue.enqueue(
            job_type="fanout_alerts",
            payload={"incident_id": str(incident.id)},
        )
        logger.info(f"Incident {incident_id} published successfully.")

    elif decision.decision == "needs_review":
        await incident_repo.update(
            incident,
            {
                "review_status": "needs_review",
                "review_reason": decision.reason or "Moderator review required",
            },
        )
        logger.info(f"Incident {incident_id} moved to needs_review.")

    elif decision.decision == "rejected":
        await incident_repo.update(
            incident,
            {
                "review_status": "rejected",
                "review_reason": decision.reason or "Report rejected during review",
            },
        )
        logger.info(f"Incident {incident_id} rejected.")
