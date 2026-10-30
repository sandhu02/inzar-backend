import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.push.provider import BasePushProvider, get_push_provider
from app.modules.alerts.repository import AlertRepository
from app.modules.categories.repository import CategoryRepository
from app.modules.incidents.repository import IncidentRepository

logger = logging.getLogger("jobs.fanout_alerts")


async def handle_fanout_alerts(
    payload: dict[str, Any],
    session: AsyncSession,
    push_provider: BasePushProvider | None = None,
) -> None:
    incident_id_str = payload.get("incident_id")
    if not incident_id_str:
        logger.error("Missing incident_id in fanout_alerts payload")
        return

    incident_id = uuid.UUID(incident_id_str)
    kind = payload.get("kind", "new")  # new, update, resolved

    incident_repo = IncidentRepository(session)
    category_repo = CategoryRepository(session)
    alert_repo = AlertRepository(session)
    provider = push_provider or get_push_provider()

    incident = await incident_repo.get_by_id(incident_id)
    if not incident or incident.review_status != "published":
        logger.info(f"Incident {incident_id} not eligible for alert fanout.")
        return

    category = await category_repo.get_by_id(incident.category_id)
    if not category:
        return

    now = datetime.now(UTC)

    # For update or resolved notifications, limit exclusively to users already notified
    if kind in ["update", "resolved"]:
        eligible_user_ids = await alert_repo.get_users_notified_for_incident(incident.id)
    else:
        # Spatial match
        matching_prefs = await alert_repo.find_spatially_matching_preferences(
            incident_lat=incident.public_lat,
            incident_lon=incident.public_lon,
        )

        eligible_user_ids = []
        for pref in matching_prefs:
            # 1. Category preference check
            if (
                pref.categories
                and str(category.id) not in pref.categories
                and category.slug not in pref.categories
            ):
                continue

            # 2. Urgency filter check
            if pref.min_urgency == "high" and category.urgency != "high":
                continue

            # 3. Duplicate notification suppression
            already_notified = await alert_repo.is_notified(
                user_id=pref.user_id,
                incident_id=incident.id,
                kind=kind,
            )
            if already_notified:
                continue

            # 4. Throttling per-user per-category (high urgency bypasses routine throttle)
            if category.urgency != "high" and category.notify_throttle_minutes > 0:
                last_time = await alert_repo.get_last_notification_time(
                    user_id=pref.user_id,
                    category_id=category.id,
                )
                if last_time:
                    throttle_window = timedelta(minutes=category.notify_throttle_minutes)
                    if (now - last_time) < throttle_window:
                        continue

            eligible_user_ids.append(pref.user_id)

    if not eligible_user_ids:
        logger.info(f"No users to notify for incident {incident_id}.")
        return

    # Fetch device tokens
    token_map = await alert_repo.get_tokens_for_users(eligible_user_ids)
    all_tokens: list[str] = []
    user_by_token: dict[str, uuid.UUID] = {}

    for uid, tokens in token_map.items():
        for t in tokens:
            all_tokens.append(t)
            user_by_token[t] = uid

    if not all_tokens:
        logger.info(f"No active device tokens found for {len(eligible_user_ids)} eligible users.")
        return

    # Build neutral push message
    if kind == "resolved":
        title = f"Resolved: {category.name}"
        body = f"The reported {category.name.lower()} incident has been marked resolved."
    elif kind == "update":
        title = f"Update: {category.name}"
        body = f"New information reported regarding {incident.title}."
    else:
        title = f"Reported Nearby: {category.name}"
        body = f"A {category.name.lower()} incident was reported in your alert radius."

    push_data = {
        "incident_id": str(incident.id),
        "kind": kind,
        "category_slug": category.slug,
    }

    successful, invalid = await provider.send_multicast(
        tokens=all_tokens,
        title=title,
        body=body,
        data=push_data,
    )

    # Prune invalid tokens
    if invalid:
        await alert_repo.prune_invalid_tokens(invalid)

    # Log successful notifications
    notified_users = {user_by_token[tok] for tok in successful if tok in user_by_token}
    for uid in notified_users:
        try:
            await alert_repo.log_notification(
                user_id=uid,
                incident_id=incident.id,
                category_id=category.id,
                kind=kind,
            )
        except Exception:
            pass

    logger.info(
        f"Alert fanout for incident {incident_id}: sent {len(successful)} pushes to {len(notified_users)} users."
    )
