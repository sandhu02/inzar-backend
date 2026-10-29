import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger("inzar.db")


def create_engine_for_url(database_url: str, is_pooled: bool = True) -> AsyncEngine:
    connect_args: dict[str, object] = {
        "timeout": 10,  # 10s connection timeout for Neon cold starts
    }

    if is_pooled:
        # Disable prepared statement cache for PgBouncer / Neon pooled connection
        connect_args["statement_cache_size"] = 0

    if settings.DATABASE_SSL:
        connect_args["ssl"] = "require"

    return create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args=connect_args,
    )


# Application engine uses pooled connection by default
engine = create_engine_for_url(settings.DATABASE_URL, is_pooled=True)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session with automatic commit/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health(retries: int = 2, delay: float = 0.5) -> tuple[bool, str]:
    """
    Check if the database is reachable and verify PostGIS is available.
    Retries once on cold start.
    """
    from sqlalchemy import text

    for attempt in range(retries + 1):
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT PostGIS_Version();"))
                version = res.scalar()
                return True, f"PostGIS {version}"
        except Exception as exc:
            logger.warning(f"DB health check attempt {attempt + 1}/{retries + 1} failed: {exc}")
            if attempt < retries:
                await asyncio.sleep(delay)
            else:
                return False, str(exc)
    return False, "Unknown error"
