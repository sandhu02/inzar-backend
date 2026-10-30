# Phase 4 Report: Map Queries, Incident Details, Flags, and Lifecycle

## 1. What Was Built
- **Database Tables & Migrations**:
  - `incident_flags`: Stores community feedback with unique constraint on `(incident_id, user_id, type)` supporting types `incorrect`, `abuse`, and `resolved`.
  - Migration `0005_incident_flags.py` created and verified.
- **Spatial Map Queries**:
  - `GET /api/v1/incidents`:
    - Radius query: Uses PostGIS `ST_DWithin` on geography with the spatial GiST index, capped by admin `max_search_radius_km`, returning relative distance in meters.
    - Bounding-box query: Supports `min_lat`, `min_lon`, `max_lat`, `max_lon` with bounding box validation.
    - Clustered mode: Spatial grid aggregation rounding coordinates to grid cells with item counts for low-zoom client performance.
    - Strict lifecycle and review filtering: Only published, active/stale, non-expired incidents are returned.
- **Public Incident Details**:
  - `GET /api/v1/incidents/{id}`:
    - Complete privacy guarantee: Surfaces fuzzed `public_lat`/`public_lon` coordinates, place label, relative age in minutes, verification label, and media thumbnail.
    - Reporter ID, email, and exact coordinates are strictly excluded from response models.
    - Returns HTTP 410 Gone for expired incidents and HTTP 404 for removed/unpublished incidents.
- **Community Flags and Corroboration**:
  - `POST /api/v1/incidents/{id}/flags`:
    - Enforces single flag per user per type.
    - Automatic demotion: When distinct abuse or incorrect flags reach `settings.abuse_flag_hide_threshold`, the report is automatically pulled from the map back to `needs_review`.
    - Community resolution: When `resolved` flags reach `category.resolve_flag_threshold`, incident lifecycle transitions to `resolved`.
    - Updates `last_confirmed_at` and marks `verification_label` as `community_corroborated`.
- **Reporter Incident Resolution**:
  - `POST /api/v1/incidents/{id}/resolve`: Allows the verified reporter (or admin/moderator) to immediately resolve their active report.
- **Background Lifecycle Sweep**:
  - `app/jobs/handlers/lifecycle.py`: Background job handler finding and marking expired incidents.

## 2. Verification
- `ruff check app`: Passed (0 errors).
- `mypy app`: Passed in strict mode (0 errors across 59 source files).

## 3. Decisions Made
- Implemented dual spatial query modes: PostGIS `ST_DWithin` for precise radius searches using the GiST index, and bounding-box queries for client map drag/zoom viewports.
- Used a rounded degree spatial grid aggregation for clustered map queries to keep payloads lightweight at low zoom levels.

