# Architecture & Technical Decisions

This document records technical and architectural choices made during development.

| Date | Decision | Reason |
|---|---|---|
| 2026-10-30 | Use `uv` with `pyproject.toml` for Python 3.12 dependency management | Fast, reproducible lockfiles, natively supports Python version management. |
| 2026-10-30 | Docker compose uses `postgis/postgis:16-3.4` | Current stable Postgres 16 image with PostGIS extension. |
| 2026-10-30 | Neon connection pooling: disable prepared statements in asyncpg (`statement_cache_size=0`) | Required by PgBouncer transaction pooling in Neon. |
| 2026-10-30 | In-memory rate limiting with clean bucket token/sliding window interface | Enables swapping with Redis or DB-backed rate limiter if needed later. |
| 2026-10-30 | Deterministic location fuzzing uses HMAC/SHA-256 seed per incident with ~200m offset | Prevents reverse-engineering exact coordinates through averaging repeated queries. |
| 2026-10-30 | Immutable category slugs and in-memory TTL caching with write invalidation | Guarantees reference consistency for reports and fast public catalog reads. |
| 2026-10-30 | Cached public lat/lon alongside PostGIS geography column | Enables fast response serialization while retaining PostGIS GiST index for spatial queries. |
| 2026-10-30 | PostgreSQL SKIP LOCKED queue with worker fallback to `needs_review` | Eliminates external Redis dependency while guaranteeing no submitted incident report is silently lost. |
| 2026-10-30 | Spatial GiST indexing with ST_DWithin and bounding-box dual query modes | Optimizes radius and viewport map lookups while supporting low-zoom grid clustering. |
| 2026-10-30 | High urgency alert bypass with strict single-incident deduplication | Alerts critical emergencies instantly while preventing spam or duplicate pushes. |
| 2026-10-30 | Full audit logging with before/after diffs on all admin and moderation writes | Provides immutable accountability across role elevations, suspensions, and incident moderation. |
| 2026-10-30 | Global ASGI SecurityHeadersMiddleware and two-service Render blueprint | Enforces defense-in-depth HTTP headers and separates web traffic from asynchronous background worker tasks. |







