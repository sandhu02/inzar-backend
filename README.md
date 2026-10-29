# Inzar Backend

Inzar is a crowdsourced, real-time local incident reporting platform backend built with FastAPI, PostgreSQL/PostGIS, and SQLAlchemy 2.0.

## Overview
Inzar enables community-driven incident reporting with map-first discovery, multi-stage review pipelines, privacy-preserving fuzzed public locations, and real-time localized push alerts.

## Requirements
- Python 3.12+ (managed with `uv`)
- PostgreSQL with PostGIS extension (or Docker for local development)
- Docker & Docker Compose (optional for local DB & containers)

## Setup & Installation

1. **Clone repository and configure environment:**
   ```bash
   cp .env.example .env
   ```

2. **Install dependencies:**
   ```bash
   uv sync --extra dev
   ```

3. **Start local PostGIS database with Docker:**
   ```bash
   docker compose up -d db
   ```

4. **Apply database migrations:**
   ```bash
   uv run alembic upgrade head
   ```

5. **Start development API server:**
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

6. **Start background job worker:**
   ```bash
   uv run python -m app.jobs.worker
   ```

## Testing & Quality Gates

Run all quality checks:
```bash
# Linting & Formatting
uv run ruff check .
uv run ruff format --check .

# Type checking
uv run mypy app

# Unit & Integration Tests
uv run pytest -q --cov=app
```

## API Documentation
Once running, OpenAPI interactive documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

