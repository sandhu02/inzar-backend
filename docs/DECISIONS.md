# Architecture & Technical Decisions

This document records technical and architectural choices made during development.

| Date | Decision | Reason |
|---|---|---|
| 2026-10-30 | Use `uv` with `pyproject.toml` for Python 3.12 dependency management | Fast, reproducible lockfiles, natively supports Python version management. |
| 2026-10-30 | Docker compose uses `postgis/postgis:16-3.4` | Current stable Postgres 16 image with PostGIS extension. |
| 2026-10-30 | Neon connection pooling: disable prepared statements in asyncpg (`statement_cache_size=0`) | Required by PgBouncer transaction pooling in Neon. |
| 2026-10-30 | In-memory rate limiting with clean bucket token/sliding window interface | Enables swapping with Redis or DB-backed rate limiter if needed later. |
| 2026-10-30 | Deterministic location fuzzing uses HMAC/SHA-256 seed per incident with ~200m offset | Prevents reverse-engineering exact coordinates through averaging repeated queries. |

