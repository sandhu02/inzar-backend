# Inzar Architecture & Design Specification

## 1. Architectural Style: Modular Monolith
Inzar is organized as a modular monolith strictly partitioned into bounded domain modules under `app/modules/`.

```
app/
├── api/
│   └── v1/router.py             # Route registration & URL mounting
├── core/
│   ├── config.py                # Typed settings (pydantic-settings)
│   ├── errors.py                # Uniform error hierarchy
│   ├── geo.py                   # Spatial validation, deterministic fuzzing
│   ├── logging.py               # Structured JSON logging & request ID
│   ├── pagination.py            # Base64 cursor pagination
│   ├── rate_limit.py            # Rate limit interfaces & in-memory sliding window
│   └── security.py              # Argon2 password hashing, JWT tokens
├── db/
│   ├── base.py                  # DeclarativeBase, UUIDPrimaryKeyMixin, Timestamps
│   ├── session.py               # Neon asyncpg engine, connection health checks
│   └── migrations/              # Alembic async migration versions
├── integrations/
│   ├── cloudinary/              # Upload signatures, asset verification, deletion
│   ├── email/                   # Resend & Console email providers
│   ├── google_auth/             # Google ID token verifier
│   ├── push/                    # FCM & Log push providers
│   └── review/                  # StubReviewProvider & review interfaces
├── jobs/
│   ├── models.py                # Job queue table model
│   ├── queue.py                 # SKIP LOCKED queue implementation
│   ├── worker.py                # Autonomous background worker process
│   └── handlers/                # Job handlers: review, lifecycle, fanout
└── modules/
    ├── admin/                   # Moderation, stats, user control, audit logging
    ├── alerts/                  # Alert preferences, device tokens, notification log
    ├── auth/                    # Signup, login, JWT rotation, email tokens
    ├── categories/              # Category catalog & admin tunables
    ├── incidents/               # Reports, media, map spatial queries, flags
    ├── settings/                # Dynamic global tunables & public config
    └── users/                   # Profiles, GDPR export, soft deletion
```

---

## 2. Layering & Cross-Module Boundaries
Strict architectural rules are validated via AST tests:
1. `router` -> `service` -> `repository`. Routers never contain business logic or query builders.
2. `repository` is the only layer touching SQLAlchemy queries (`select`, `insert`, `update`, `delete`).
3. Modules never import another module's repository for writes. All cross-module actions flow through public service functions.
4. Integrations (`Cloudinary`, `Push`, `Review`, `Email`) are behind abstract interfaces injected with FastAPI dependencies.

---

## 3. Privacy-First Geo Architecture
- **Location Storage**:
  - `location_exact`: PostGIS Geography Point(4326) stored privately for internal corroboration. Never returned in public responses.
  - `location_public`: PostGIS Geography Point(4326) deterministically fuzzed by ~200m using per-incident HMAC/SHA-256 seeding. Repeated reads always return the identical fuzzed coordinate, preventing triangulation through averaging.
  - `public_lat` & `public_lon`: Cached float values indexed on the table for zero-overhead JSON serialization.
- **Spatial Indexing**:
  - PostGIS GiST index on `incidents.location_public` and `alert_preferences.center`.
  - Radius queries utilize `ST_DWithin` on geography, ensuring accurate distance calculations across the Earth's curvature.

---

## 4. Background Job Queue (PostgreSQL SKIP LOCKED)
To avoid an external Redis infrastructure dependency on Render, Inzar uses PostgreSQL with `FOR UPDATE SKIP LOCKED`:
- Atomic job claiming with worker IDs and lock timestamps.
- Lock expiration recovery for crashed worker processes.
- Exponential backoff retries with transition to `dead_letter`.
- Dedicated worker process running `app.jobs.worker`.

