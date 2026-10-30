# Phase 3 Report: Media and Incident Submission with Review Pipeline

## 1. What Was Built
- **Database Tables & Migrations**:
  - `incidents`: UUID primary key, reporter foreign key (nullable), active category reference, title, description, PostGIS geography points (`location_exact` and `location_public`), cached public lat/lon, place label, review status (`awaiting_media`, `checking`, `published`, `needs_review`, `rejected`, `review_unavailable`), review reason, verification label (`none`, `ai_reviewed`, `community_corroborated`), lifecycle status (`active`, `stale`, `expired`, `resolved`), and timestamps.
  - Spatial GiST index on `location_public` and composite BTree index on `(review_status, lifecycle_status, published_at)`.
  - `incident_media`: Cloudinary asset tracking with status (`pending`, `confirmed`, `failed`), image dimensions, format, bytes, and secure URL.
  - `jobs`: PostgreSQL-backed job queue table with status (`queued`, `running`, `completed`, `failed`, `dead_letter`), payload, run_at, attempt counts, lock metadata, and error details.
  - Migration `0004_incidents_media_jobs.py` applied.
- **Integrations**:
  - `BaseCloudinaryService` with `CloudinaryService` and `FakeCloudinaryService`: Server-signed direct upload parameters scoped per incident, asset verification against Cloudinary Admin API, and asset deletion.
  - `BaseReviewProvider` with `StubReviewProvider` and `FakeReviewProvider`: Implements section 6.5 review policy respecting `review_mode` and category `require_manual_review` without calling external AI models.
- **Incident Reporting & Review Pipeline**:
  - `POST /api/v1/incidents`: Validates active category, description length limits, coordinates, minimum account age, suspended user status, user hourly submission rate limits, generates deterministic ~200m fuzzed coordinates, persists incident as `awaiting_media`, and returns signed Cloudinary parameters.
  - `POST /api/v1/incidents/{id}/media/confirm`: Verifies uploaded image with Cloudinary, creates `incident_media` record, transitions incident to `checking`, enqueues background `review_incident` job, and supports idempotent retries.
  - `GET /api/v1/incidents/{id}/status`: Surfaces current review and verification status.
  - `POST /api/v1/incidents/{id}/resubmit`: Allows resubmission for rejected reports with new metadata or photos.
  - `GET /api/v1/me/incidents`: Lists incidents submitted by the authenticated user with status filters.
- **Background Worker & Job Queue**:
  - `JobQueue` implementing atomic job claiming with `SELECT ... FOR UPDATE SKIP LOCKED` and lock timeout recovery.
  - Exponential backoff retry mechanism (5s, 20s, 80s) and transition to `dead_letter` after max attempts.
  - `review_incident` job handler with fallback to `needs_review` when provider fails after retries, ensuring reports are never lost.
  - `app/jobs/worker.py` daemon entrypoint with graceful shutdown handling.

## 2. Verification
- `ruff check app`: Passed (0 errors).
- `mypy app`: Passed in strict mode (0 errors across 57 source files).

## 3. Decisions Made
- Stored `public_lat` and `public_lon` float columns alongside PostGIS `location_public` geography point for sub-millisecond serialization without repeated spatial geometry unmarshaling.
- Applied `FOR UPDATE SKIP LOCKED` on queue jobs to support concurrent horizontal worker scalability without Redis.
- Implemented automatic fallback to `needs_review` upon review failure so that incidents are never dropped.

