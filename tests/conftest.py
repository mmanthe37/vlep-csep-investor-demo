"""
Pytest configuration and shared fixtures for VLEP pipeline tests.

Key fixtures:
  db_session   — per-test async SQLAlchemy session bound to a rolled-back
                 connection (no data persists between tests).
  async_client — per-test httpx.AsyncClient mounted on the FastAPI app with
                 the test db_session injected via dependency_overrides.
                 Includes default clinical_director-role auth headers.

Architecture note on session scoping
--------------------------------------
``asyncio_mode = "auto"`` in pyproject.toml means pytest-asyncio manages the
event loop. We deliberately use ``scope="function"`` for *both* test_engine and
db_session so that each test gets a fresh connection and a fresh rolled-back
transaction. The slight overhead is worth the complete test isolation.

The ``session``-scoped engine approach would require
``asyncio_default_fixture_loop_scope = "session"`` in pyproject.toml which
conflicts with function-scoped fixtures used in test_*.py files. We keep
everything function-scoped for simplicity and correctness.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from vlep.api.deps import get_db
from vlep.config import get_settings

# ── Per-test rolled-back DB session ─────────────────────────────────────────

@pytest.fixture
async def db_session():
    """Yield an isolated async session.

    Creates its own engine (NullPool — no connection reuse) and a top-level
    transaction per test. All writes are rolled back when the test finishes.
    """
    settings = get_settings()
    # NullPool: one connection per engine instance, no pooling — eliminates
    # cross-test connection interference in concurrent fixture teardown.
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)

    connection = await engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        # Use savepoints so that tests can call session.flush() without
        # accidentally committing to the outer rolled-back transaction.
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()
    await engine.dispose()


# ── HTTP test client (router tests) ─────────────────────────────────────────

@pytest.fixture
async def async_client(db_session: AsyncSession):
    """Yield an httpx.AsyncClient wired to the FastAPI app.

    The app's ``get_db`` dependency is overridden to return the same
    rolled-back ``db_session`` so router tests see the same data as service
    tests — and all writes are discarded after each test.

    Default headers identify the caller as a ``clinical_director`` so that
    all RBAC gates pass unless a specific test needs to exercise a lower role.
    """
    from vlep.api.main import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    default_headers = {
        "X-Actor-ID": "test_director",
        "X-Actor-Role": "clinical_director",
        "X-Access-Reason": "automated_test",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=default_headers,
    ) as client:
        yield client
