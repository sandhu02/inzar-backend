# Phase 5 Report: Alerts and Push Notifications

## 1. What Was Built
- **Database Tables & Migrations**:
  - `alert_preferences`: User alert settings storing enabled flag, coarse center geography point, center_lat/lon, radius in km, subscribed category IDs (JSONB), and minimum urgency threshold (`routine`/`high`).
  - Spatial GiST index on `alert_preferences.center`.
  - `device_tokens`: Unique device push token registry per user with platform tag (`android`, `ios`, `web`) and `last_seen_at` tracking.
  - `notification_log`: Deduping log with unique constraint on `(user_id, incident_id, kind)`.
  - Migration `0006_alerts_and_push.py` applied.
- **Push Integrations**:
  - `BasePushProvider`: Interface defining `send_multicast(tokens, title, body, data) -> (successful, invalid)`.
  - `LogPushProvider`: Development and testing provider outputting push logs.
  - `FcmPushProvider`: Firebase Cloud Messaging HTTP v1 provider with service account support.
  - `FakePushProvider`: In-memory test spy tracking sent notifications and prune lists.
- **Alert Endpoints**:
  - `GET /api/v1/me/alert-preferences`: Retrieves user alert configurations.
  - `PUT /api/v1/me/alert-preferences`: Updates alert center coordinates, radius, categories, and urgency.
  - `POST /api/v1/me/devices`: Registers or updates device push tokens.
  - `DELETE /api/v1/me/devices/{token}`: Unregisters device push tokens.
- **Spatial Fan-out and Intelligent Throttling**:
  - `app/jobs/handlers/fanout_alerts.py`:
    - Executes single spatial query `ST_DWithin` matching incident location against all active user alert radii.
    - Matches category filters and minimum urgency thresholds.
    - Prevents duplicates via `notification_log` lookup.
    - Applies per-category throttling (`category.notify_throttle_minutes`), with `high` urgency bypassing routine rate limits while preserving duplicate suppression.
    - Neutral notification phrasing (never claiming official confirmation or imminent danger).
    - Automatic token pruning: Invalid tokens returned by provider are pruned from `device_tokens`.

## 2. Verification
- `ruff check app`: Passed (0 errors).
- `mypy app`: Passed in strict mode (0 errors across 67 source files).

## 3. Decisions Made
- `high` urgency incident notifications bypass per-category throttle windows, ensuring rapid awareness of critical emergencies without sending duplicate notifications.
- Push tokens rejected by providers are pruned from the database immediately to keep recipient lists clean.

