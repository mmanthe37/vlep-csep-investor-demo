"""
VLEP Pipeline — FastAPI Application Factory.

Creates and configures the VLEP REST API with:
  - OpenAPI documentation (Swagger UI + ReDoc)
  - CORS for local development
  - Auth middleware (OIDC stub)
  - HIPAA governance audit middleware
  - All 6 domain routers
  - Health and readiness endpoints
  - Structured lifespan (DB startup check)
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vlep.api.middleware.audit import GovernanceAuditMiddleware
from vlep.api.middleware.auth import AuthMiddleware
from vlep.api.routers import (
    csep_router,
    evidence_router,
    governance_router,
    literature_router,
    patients_router,
    phenotypes_router,
)
from vlep.api.routers.system import router as system_router
from vlep.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown logic."""
    # Startup: verify DB connection is reachable
    logger.info("VLEP API starting up (v%s)", settings.api_version)
    try:
        from sqlalchemy import text

        from vlep.db import async_engine
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connectivity confirmed.")
    except Exception as exc:
        logger.error("Database connectivity check failed: %s", exc)
        # Do not raise — allow the app to start even if DB is temporarily unavailable

    yield

    # Shutdown: dispose connection pool
    logger.info("VLEP API shutting down — disposing connection pool.")
    from vlep.db import async_engine
    await async_engine.dispose()


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Construct and configure the VLEP FastAPI application.

    Returns a fully configured ``FastAPI`` instance ready for ASGI deployment
    (uvicorn, gunicorn+uvicorn worker, or testing with ``httpx.AsyncClient``).
    """
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=_API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=_OPENAPI_TAGS,
    )

    # ── Middleware (applied in reverse order — last added executes first) ──
    # 1. CORS (outermost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],           # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Auth (validates JWT / populates request.state.principal)
    app.add_middleware(AuthMiddleware)

    # 3. Governance audit (logs patient data accesses to governance.access_logs)
    app.add_middleware(GovernanceAuditMiddleware)

    # ── Routers ────────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"
    app.include_router(patients_router,   prefix=API_PREFIX)
    app.include_router(evidence_router,   prefix=API_PREFIX)
    app.include_router(literature_router, prefix=API_PREFIX)
    app.include_router(phenotypes_router, prefix=API_PREFIX)
    app.include_router(csep_router,       prefix=API_PREFIX)
    app.include_router(governance_router, prefix=API_PREFIX)
    app.include_router(system_router,     prefix=API_PREFIX)

    # ── Health / utility endpoints ─────────────────────────────────────────
    @app.get("/", tags=["System"], summary="Root — API info")
    async def root() -> dict:
        return {
            "name": settings.api_title,
            "version": settings.api_version,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["System"], summary="Health check")
    async def health() -> dict:
        """Lightweight liveness probe — returns 200 if the process is running."""
        return {"status": "ok", "version": settings.api_version}

    @app.get("/health/db", tags=["System"], summary="Database readiness probe")
    async def health_db() -> JSONResponse:
        """Checks that the async DB engine can execute a query."""
        try:
            from sqlalchemy import text

            from vlep.db import async_engine
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok", "database": "reachable"})
        except Exception as exc:
            logger.error("DB health check failed: %s", exc)
            return JSONResponse(
                {"status": "error", "database": "unreachable", "detail": str(exc)},
                status_code=503,
            )

    # ── Request timing middleware ──────────────────────────────────────────
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response

    # ── Global exception handler ───────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            {"detail": "An unexpected internal error occurred.", "type": type(exc).__name__},
            status_code=500,
        )

    return app


# ── OpenAPI metadata ──────────────────────────────────────────────────────────

_API_DESCRIPTION = """
## VLEP Pipeline REST API

The **Versioned Longitudinal Epilepsy Phenotype (VLEP)** platform exposes a
complete REST API for ingesting heterogeneous clinical data, managing the
immutable evidence ledger, asserting formal phenotype labels, running the LPA
longitudinal modeling engine, assembling Current-State Epilepsy Profiles (CSEP),
and enforcing governance / HIPAA audit controls.

### Architecture

| Symbol | Component | Purpose |
|--------|-----------|---------|
| **𝓛** | Immutable Evidence Ledger | Append-only, SHA-256 chained truth store |
| **𝓝** | Nosological Framework | Versioned ILAE classification taxonomy |
| **F** | Resolution Function | Deterministic CSEP profile assembly |
| **P** | Current-State Epilepsy Profile | Clinician-facing versioned output |

### Authentication

All endpoints (except `/`, `/health`, `/docs`, `/redoc`) require either:
- `Authorization: Bearer <token>` header (production OIDC JWT)
- `X-Actor-ID` + `X-Actor-Role` headers (development stub)

### Role Hierarchy

`readonly < clinic_nurse < clinician < epileptologist < clinical_director < admin`
"""

_OPENAPI_TAGS = [
    {"name": "System", "description": "Health probes and API metadata"},
    {"name": "Patients", "description": "Pseudonymous patient identity management"},
    {"name": "Evidence Ledger", "description": "Immutable SHA-256 chained evidence ledger"},
    {"name": "Literature & Claims", "description": "Biomedical document ingestion and phenotype claim extraction"},
    {"name": "Phenotypes", "description": "Phenotype assertions and temporal feature engineering"},
    {"name": "CSEP Profiles", "description": "Current-State Epilepsy Profile assembly and nosological reversioning"},
    {"name": "Governance & Safety", "description": "HIPAA audit logs, review tasks, data quality, and model drift"},
]


# ── Entry point for uvicorn ───────────────────────────────────────────────────

# Create the application instance at module level so uvicorn can import it:
#   uvicorn vlep.api.main:app --reload
app = create_app()
