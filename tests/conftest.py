from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.session import get_db
from app.integrations.email.provider import get_email_provider
from app.integrations.google_auth.verifier import (
    get_google_auth_verifier,
)
from app.main import create_app
from tests.fakes import FakeEmailProvider, FakeGoogleAuthVerifier


def get_test_engine():
    return create_async_engine(
        settings.TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
        connect_args={"statement_cache_size": 0},
    )


@pytest.fixture
def fake_email() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture
def fake_google() -> FakeGoogleAuthVerifier:
    return FakeGoogleAuthVerifier()


@pytest.fixture(autouse=True)
async def clean_database():
    """Truncate tables before each test to ensure complete isolation."""
    engine = get_test_engine()
    async with engine.begin() as conn:
        # Check which tables exist and truncate them
        for table in ["email_tokens", "refresh_tokens", "users"]:
            try:
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
            except Exception:
                pass
    await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a database session for test helpers."""
    engine = get_test_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


@pytest.fixture
async def client(
    fake_email: FakeEmailProvider,
    fake_google: FakeGoogleAuthVerifier,
) -> AsyncGenerator[AsyncClient, None]:
    """Test client with isolated engine and dependency overrides."""
    engine = get_test_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_email_provider] = lambda: fake_email
    app.dependency_overrides[get_google_auth_verifier] = lambda: fake_google

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
