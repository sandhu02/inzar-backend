# CLAUDE.md - Inzar Backend Project Instructions & Progress

## Project Overview
Inzar is a crowdsourced, real-time local incident reporting platform backend (FastAPI + PostgreSQL with PostGIS).
The platform allows mobile users to report local incidents with photos, review them through a verification pipeline, and serve them to a map-first client filtered by radius and category.

## Technology Stack
- **Language**: Python 3.12 (managed via `uv`)
- **Framework**: FastAPI, Uvicorn (Gunicorn with Uvicorn workers for production)
- **Database**: PostgreSQL with PostGIS extension (Neon in cloud, local PostGIS container for dev/test)
- **ORM / Migrations**: SQLAlchemy 2.0 async, asyncpg, GeoAlchemy2, Alembic
- **Validation & Settings**: Pydantic v2, pydantic-settings
- **Auth & Crypto**: Argon2 (argon2-cffi), PyJWT, Google Auth ID token verification
- **Integrations**: Cloudinary (signed direct uploads), Resend (email), FCM (push), ReviewProvider (stubbed)
- **Background Tasks**: PostgreSQL-backed job queue (`SKIP LOCKED`) + dedicated worker process
- **Code Quality & Testing**: ruff (lint & format), mypy (strict), pytest, pytest-asyncio, httpx, factory/faker

## Architecture & Layering Rules
- **Modular Monolith**: Modules under `app/modules/<module>/` contain `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `dependencies.py`, `constants.py`.
- **Strict Layering**: `router` -> `service` -> `repository`. Routers contain no business logic and no database queries.
- **Repository Isolation**: `repository` is the only code that touches SQLAlchemy queries.
- **Cross-module interactions**: Never import another module's repository or models for writes; call the other module's public service functions.
- **Integrations**: Access behind abstract interfaces (`app/integrations/`) injected via FastAPI dependencies.
- **Privacy by Default**: Never leak reporter identity, email, or exact coordinates (`location_exact`) in public responses. Fuzzed public coordinates (`location_public`, ~200m deterministic jitter) are used for map views.
- **Unified Error Response**: `{"error": {"code": "string", "message": "human readable", "details": {}}}`.
- **IDs & Datetimes**: UUIDs for primary keys; timezone-aware UTC datetimes.

## Essential Commands

### Environment & Dependencies
```bash
# Sync / install dependencies
uv sync

# Run tool via uv
uv run <command>
```

### Linting & Type Checking
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

### Testing
```bash
# Full test suite with coverage
uv run pytest -q --cov=app

# Run specific test file
uv run pytest tests/unit/test_imports.py -v
```

### Database Migrations
```bash
# Run migrations using direct connection
uv run alembic upgrade head

# Rollback one revision
uv run alembic downgrade -1

# Generate a new migration
uv run alembic revision --autogenerate -m "migration_name"
```

### Running Server & Worker
```bash
# Run API server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run background worker
uv run python -m app.jobs.worker
```

## Phase Implementation Tracker

| Phase | Description | Status | Verification & Deliverables |
|---|---|---|---|
| **Phase 0** | Foundation (Skeleton, Config, DB, PostGIS, Errors, Logging, Health, Docker, CI, Import tests) | Completed | App boots, `/healthz` & `/readyz`, Alembic up/down, import boundaries pass |
| **Phase 1** | Auth & Users (Argon2, JWT, Google Auth, Refresh token rotation, Email tokens, Me endpoints) | Completed | Full auth matrix, token reuse revocation, role dependencies, CLI admin |
| **Phase 2** | Categories & Settings (Admin tunables, Seed defaults, Public endpoints, Cache, Audit logging) | Completed | Category CRUD, global tunables, audit logs, seed idempotency (`docs/phases/phase-2-report.md`) |
| **Phase 3** | Media & Incident Submission + Review Pipeline (Cloudinary signatures, PG queue, Review stub) | Completed | Submit -> upload -> confirm -> review pipeline -> status check (`docs/phases/phase-3-report.md`) |
| **Phase 4** | Map Queries, Details, Flags, Lifecycle (ST_DWithin, Cursor pagination, Flags, Auto-stale/expire) | Completed | Spatial queries, clustering, lifecycle jobs, corroboration/abuse thresholds (`docs/phases/phase-4-report.md`) |
| **Phase 5** | Alerts & Push (Preferences, FCM/Log providers, Spatial fanout, Throttling, Digests) | Completed | Spatial fanout query, deduplication, rate limits, neutral notifications (`docs/phases/phase-5-report.md`) |
| **Phase 6** | Admin & Moderation Backend (Queue, Approve/Reject, Users, Flags, Dead-letter jobs, Stats) | Completed | Role matrix, audit logs, moderation actions, stats overview (`docs/phases/phase-6-report.md`) |
| **Phase 7** | Hardening & Render Deployment (Security pass, Render blueprint, Docker, Docs, OpenAPI export) | Completed | Security headers, Render blueprint, docs/API.md, openapi.json (`docs/phases/phase-7-report.md`) |
