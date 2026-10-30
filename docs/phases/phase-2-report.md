# Phase 2 Report: Categories and Global Settings (Admin Tunables)

## 1. What Was Built
- **Database Tables & Migrations**:
  - `categories`: UUID primary key, immutable unique `slug`, `name`, `icon_key`, `color_hex`, `sort_order`, `is_active`, `urgency` (`routine`/`high`), `default_ttl_minutes`, `stale_after_minutes`, `resolve_flag_threshold`, `notify_throttle_minutes`, `notify_by_default`, `require_manual_review`, `safety_note`, and timestamps.
  - `app_settings`: Key-value configuration table with JSONB value, description, updated_by user foreign key, and timestamp.
  - `audit_log`: Audit tracking table storing actor ID, action name, target type and ID, and before/after summary in JSONB.
  - Migration `0003_categories_settings_audit.py` creating tables and indexes.
- **Category Management**:
  - Public `GET /api/v1/categories`: Lists only active categories, sorted by `sort_order` then `name`, served with a short-lived in-memory cache.
  - Admin `GET /api/v1/admin/categories`: Lists all categories including inactive ones.
  - Admin `POST /api/v1/admin/categories`: Creates a new category with strict slug formatting, hex color validation, numeric range checks (`stale_after_minutes <= default_ttl_minutes`), and automatic audit log generation.
  - Admin `PATCH /api/v1/admin/categories/{id}`: Updates any tunable field while preserving immutable slug, invalidating the in-memory cache, and recording before/after audit entries.
  - Deactivation rule respected: Categories are flagged inactive rather than hard-deleted.
- **Global Settings & Public Config**:
  - Typed `GlobalSettingsSchema` with validation ranges for: `max_search_radius_km`, `allowed_radius_options_km`, `fuzz_distance_m`, `max_reports_per_user_per_hour`, `max_description_length`, `review_mode` (`auto_approve`/`manual`), `abuse_flag_hide_threshold`, `alert_digest_threshold`, `alert_digest_window_minutes`, and `min_account_age_minutes_to_report`.
  - Public `GET /api/v1/config`: Surfaces public configuration limits (`max_search_radius_km`, `allowed_radius_options_km`, `max_description_length`, `fuzz_distance_m`).
  - Admin `GET /api/v1/admin/settings`: Retrieves all global tunables.
  - Admin `PATCH /api/v1/admin/settings`: Validates and persists partial updates, invalidates cache, and creates audit log records.
- **Audit Logging**:
  - `AdminService` and `AdminRepository` logging actions for category creation, category updates, and settings changes.
  - Admin `GET /api/v1/admin/audit-log`: Filterable audit log endpoint.
- **Idempotent Seeding**:
  - Built-in seeder for the 6 initial default categories (`fire`, `accident`, `road_blockage`, `flooding`, `public_gathering`, `other_hazard`) and default global settings.
  - CLI command: `uv run python -m app.cli seed`.

## 2. Verification
- `ruff check app`: Passed (0 errors).
- `mypy app`: Passed in strict mode (0 errors across 46 source files).

## 3. Decisions Made
- Category slugs are strictly immutable after creation to protect incident foreign references and URL stability.
- Cross-field validation ensures `stale_after_minutes` cannot exceed `default_ttl_minutes` on category creation and updates.
- In-memory caching with TTL (60s) and write invalidation implemented for both categories and settings for fast query responses.

