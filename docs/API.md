# Inzar Backend API Reference

Base URL: `/api/v1`

All responses follow uniform JSON error envelopes:
```json
{
  "error": {
    "code": "machine_readable_code",
    "message": "Human readable error description",
    "details": {}
  }
}
```

---

## 1. Authentication & Users

### `POST /api/v1/auth/signup`
Creates a new account with email and strong password.
- **Body**: `{ "email": "...", "password": "...", "display_name": "..." }`
- **Response (201)**: User object with tokens.

### `POST /api/v1/auth/login`
Authenticates with email and password. Protected with constant-time validation to prevent user enumeration.
- **Body**: `{ "email": "...", "password": "..." }`
- **Response (200)**: `{ "access_token": "...", "refresh_token": "...", "user": {...} }`

### `POST /api/v1/auth/google`
Authenticates with Google ID token.
- **Body**: `{ "id_token": "..." }`
- **Response (200)**: Auth tokens and profile.

### `POST /api/v1/auth/refresh`
Rotates refresh token. If token reuse is detected, all tokens in the family are revoked immediately.
- **Body**: `{ "refresh_token": "..." }`
- **Response (200)**: Rotated access and refresh tokens.

### `POST /api/v1/auth/logout`
Revokes the current refresh token.
- **Body**: `{ "refresh_token": "..." }`
- **Response (204)**: No Content.

### `GET /api/v1/me`
Retrieves authenticated user profile.

### `PATCH /api/v1/me`
Updates display name.

### `DELETE /api/v1/me`
Soft-deletes user account and revokes access tokens immediately.

---

## 2. Categories & Configuration

### `GET /api/v1/categories` (Public)
Lists all active incident categories ordered by sort order and name. Cached with short TTL.
- **Response (200)**: List of categories with slug, name, icon key, color, and urgency.

### `GET /api/v1/config` (Public)
Returns client configuration constants (max search radius, allowed radius presets, fuzz distance).

---

## 3. Incidents & Reporting

### `POST /api/v1/incidents` (Auth)
Submits a new incident report and returns signed Cloudinary direct upload parameters.
- **Body**:
  ```json
  {
    "category_id": "uuid",
    "title": "Road hazard near 5th ave",
    "description": "Fallen tree blocking the north lane",
    "latitude": 40.7128,
    "longitude": -74.0060,
    "place_label": "Downtown"
  }
  ```
- **Response (201)**:
  ```json
  {
    "incident_id": "uuid",
    "review_status": "awaiting_media",
    "upload_params": {
      "upload_url": "https://api.cloudinary.com/...",
      "api_key": "...",
      "timestamp": 1730000000,
      "folder": "inzar/incidents/uuid",
      "signature": "..."
    }
  }
  ```

### `POST /api/v1/incidents/{id}/media/confirm` (Auth)
Confirms image upload with Cloudinary and advances status to `checking`, queuing background review.
- **Body**:
  ```json
  {
    "cloudinary_public_id": "inzar/incidents/...",
    "secure_url": "https://res.cloudinary.com/...",
    "width": 1920,
    "height": 1080
  }
  ```

### `GET /api/v1/incidents/{id}/status` (Public)
Returns current review and lifecycle status of an incident.

### `POST /api/v1/incidents/{id}/resubmit` (Auth)
Allows reporter to update metadata or obtain a new upload signature for a rejected incident report.

### `GET /api/v1/me/incidents` (Auth)
Retrieves incidents submitted by the current authenticated user, filterable by `review_status`.

---

## 4. Map & Details

### `GET /api/v1/incidents` (Public)
Spatial query for active published incidents using PostGIS `ST_DWithin` or bounding box.
- **Query Params**:
  - `lat`, `lon`, `radius_km` (Radius search) OR
  - `min_lat`, `min_lon`, `max_lat`, `max_lon` (Bounding box)
  - `category_id`: optional UUID
  - `clustered`: boolean (grid clustering for low zoom)
- **Response (200)**: List of map items with relative distance, age in minutes, and thumbnail URL.

### `GET /api/v1/incidents/{id}` (Public)
Detailed public incident information. Never exposes reporter ID, email, or exact coordinates. Returns 410 Gone if expired.

### `POST /api/v1/incidents/{id}/flags` (Auth)
Flag an incident as `incorrect`, `abuse`, or `resolved`.
- Abuse flags reaching `abuse_flag_hide_threshold` automatically remove the incident back to `needs_review`.
- Community resolved flags reaching `resolve_flag_threshold` resolve the incident.

### `POST /api/v1/incidents/{id}/resolve` (Auth)
Reporter or moderator directly marks their incident resolved.

---

## 5. Alerts & Push

### `GET /api/v1/me/alert-preferences` (Auth)
Gets user alert center, radius, categories, and urgency settings.

### `PUT /api/v1/me/alert-preferences` (Auth)
Updates alert preferences.

### `POST /api/v1/me/devices` (Auth)
Registers push device token (`android`, `ios`, `web`).

### `DELETE /api/v1/me/devices/{token}` (Auth)
Unregisters push device token.

---

## 6. Admin & Moderation

- `GET /api/v1/admin/moderation/queue`: Moderation review queue.
- `POST /api/v1/admin/moderation/{id}/approve`: Approve report -> published.
- `POST /api/v1/admin/moderation/{id}/reject`: Reject report with mandatory reason.
- `GET /api/v1/admin/flags`: Review reported community flags.
- `PATCH /api/v1/admin/flags/{id}`: Dismiss flag.
- `GET /api/v1/admin/users`: Search users and view report counts.
- `PATCH /api/v1/admin/users/{id}`: Suspend/unsuspend account or update role (`admin`, `moderator`).
- `GET /api/v1/admin/categories`: Admin category CRUD.
- `POST /api/v1/admin/categories`: Create category with tunable parameters.
- `PATCH /api/v1/admin/categories/{id}`: Update category tunables.
- `GET /api/v1/admin/settings`: View global tunables.
- `PATCH /api/v1/admin/settings`: Update global tunables.
- `GET /api/v1/admin/stats/overview`: Real-time system metrics.
- `GET /api/v1/admin/jobs`: Inspect background queue.
- `POST /api/v1/admin/jobs/{id}/retry`: Retry failed/dead-letter job.
- `GET /api/v1/admin/audit-log`: Immutable security and moderation audit log.

