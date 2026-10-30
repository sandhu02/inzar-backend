# Inzar Backend Deployment Guide (Render & Neon)

This guide covers production deployment on Render with a Neon PostgreSQL database.

---

## 1. Neon Database Setup

1. Create a Neon PostgreSQL 16 project.
2. In the Neon Console, obtain two connection strings:
   - **Pooled connection string**: Used by the FastAPI web service and background worker (`DATABASE_URL`).
   - **Direct connection string**: Used by Alembic database migrations (`DATABASE_URL_DIRECT`).
3. Ensure the direct connection string is used for migrations to allow schema DDL changes without PgBouncer session restrictions.
4. Enable PostGIS extension: Migration `0001_enable_postgis.py` runs `CREATE EXTENSION IF NOT EXISTS postgis;` automatically.

---

## 2. Render Deployment via Blueprint

`render.yaml` declares the full environment:

### Step 1: Connect GitHub Repository
1. Navigate to the Render Dashboard -> **Blueprints** -> **New Blueprint Instance**.
2. Select the repository containing `render.yaml`.

### Step 2: Configure Environment Variables
Set the following secrets in the Render Dashboard:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Neon pooled connection string with `postgresql+asyncpg://` |
| `DATABASE_URL_DIRECT` | Neon direct connection string with `postgresql+asyncpg://` |
| `DATABASE_SSL` | `true` |
| `SECRET_KEY` | At least 32-character random cryptographic secret |
| `CORS_ORIGINS` | Web admin URL (e.g. `https://admin.inzar.app`) |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `RESEND_API_KEY` | Resend API key for transactional emails |
| `FCM_PROJECT_ID` | Firebase project ID |
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase service account credentials JSON string |

### Step 3: Deploy
Render will automatically:
1. Run pre-deploy migration: `alembic upgrade head`.
2. Build and launch `inzar-backend-api` on the assigned `$PORT`.
3. Launch `inzar-backend-worker` background process executing `python -m app.jobs.worker`.

---

## 3. Post-Deployment Verification

1. Health Check:
   ```bash
   curl -i https://<your-render-service>.onrender.com/healthz
   # Expect HTTP 200 OK {"status": "ok"}
   ```
2. Readiness Check:
   ```bash
   curl -i https://<your-render-service>.onrender.com/readyz
   # Expect HTTP 200 OK with PostGIS version string
   ```
3. Bootstrap Admin User:
   Access Render SSH or run via CLI:
   ```bash
   python -m app.cli create-admin --email admin@inzar.app --password "YourStrongAdminPassword#2026"
   python -m app.cli seed
   ```

