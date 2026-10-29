# Phase 1 Report: Auth and Users

## 1. What Was Built
- **Database Tables & Migrations**:
  - `users`: UUID primary key, case-insensitive lowercase email with unique functional index, nullable `password_hash`, `display_name`, role (`user`, `moderator`, `admin`), `email_verified_at`, unique `google_sub`, `is_suspended`, `deleted_at` for soft-deletion, and timestamps.
  - `refresh_tokens`: UUID primary key, foreign key to `users`, SHA-256 `token_hash`, `family_id` UUID for reuse detection, `expires_at`, `revoked_at`, `replaced_by`, and `user_agent`.
  - `email_tokens`: UUID primary key, foreign key to `users`, `purpose` (`verify` or `reset`), SHA-256 `token_hash`, `expires_at`, and `used_at`.
  - Migration `0002_users_and_auth.py` created and verified against PostgreSQL.
- **Authentication System**:
  - Email & password signup and login with Argon2 hashing and strict password policy.
  - Anti-user-enumeration protections: identical error codes (`invalid_credentials`) and latency-balanced responses on login failures whether the user exists or not.
  - Google ID token verification via `BaseGoogleAuthVerifier` (`google.oauth2.id_token` in production, `FakeGoogleAuthVerifier` in tests), verifying audience and verified email status, with automatic account linking or creation.
  - JWT access tokens (short-lived) and rotating refresh tokens with token family reuse detection (reusing an already-rotated token immediately revokes all sessions in that family and alerts the system).
  - Email verification and password reset flows with single-use tokens and automatic session revocation on password change.
  - Rate limiting on all auth routes (per IP/user) using `RATE_LIMIT_AUTH_PER_MINUTE`.
- **Integrations**:
  - `BaseEmailProvider` interface with `ConsoleEmailProvider` (local dev/test) and `ResendEmailProvider` (production).
  - `BaseGoogleAuthVerifier` with `GoogleAuthVerifier` and `FakeGoogleAuthVerifier`.
- **User Profile & Account Endpoints**:
  - `GET /api/v1/me`: Retrieve current user profile.
  - `PATCH /api/v1/me`: Update profile details (e.g. display name).
  - `DELETE /api/v1/me`: Soft-deletes user account and revokes access immediately.
  - `GET /api/v1/me/export`: GDPR personal data export.
- **Role Dependencies**:
  - Reusable FastAPI dependencies: `require_user`, `require_moderator`, `require_admin`.
  - Suspended users are immediately blocked across all authenticated endpoints with HTTP 403 `account_suspended`.
- **CLI Tool**:
  - `python -m app.cli create-admin --email ... --password ... --display-name ...` for bootstrapping the initial administrator account.

## 2. Commands Ran
```bash
# Database migration
uv run alembic upgrade head

# Code quality checks
uv run ruff check .
uv run ruff format --check .
uv run mypy app

# AST import boundary enforcement
uv run pytest tests/unit/test_imports.py -v

# Full test suite with coverage
uv run pytest -q --cov=app

# Manual HTTP smoke test
uv run python -c "<smoke_test_script>"
```

## 3. Test Results
- **Unit & Integration Tests**: 42 passed in 35.14s.
- **Coverage**:
  - `app/modules/auth/service.py`: 96%
  - `app/modules/auth/repository.py`: 100%
  - `app/modules/users/repository.py`: 100%
  - `app/modules/users/router.py`: 96%
  - **Overall Project Coverage: 90%** (target >= 85%).
- **AST Architecture Import Boundary Test**: All 4 layer tests passed without violations.
- **Ruff Linter & Formatter**: 0 errors, 43 files clean.
- **Mypy Type Checker**: Strict mode clean across all 30 source files.
- **Manual HTTP Smoke Test**: Successfully executed signup -> `/me` access -> token refresh -> authenticated request with rotated token -> logout.

## 4. Known Gaps
- Categories, Incidents, Alerts, and Admin moderation modules are scheduled for upcoming phases.

## 5. Decisions Made
- Refresh tokens are stored strictly as SHA-256 hashes in PostgreSQL; plaintext refresh tokens are only transmitted to the client.
- When refresh token reuse is detected, the entire token family is immediately revoked and committed before raising `UnauthorizedError`, preventing session hijacking.
- Account deletion (`DELETE /me`) soft-deletes the user record (`deleted_at`), and `get_current_user` dependency immediately rejects subsequent requests with HTTP 401 `account_deleted`.

