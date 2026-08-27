"""
VLEP Pipeline — System & Gordon API Router.

Endpoints for Docker's Gordon AI assistant and system administrators
to monitor queue health, GPU utilization, CSEP ledger integrity, and auto-scaling.

Routes
------
GET    /system/gordon/health               Gordon primary diagnostic endpoint
GET    /system/gordon/queues               Celery queue depth and NLP latency
GET    /system/gordon/ledger/verify        Verify cryptographic integrity of CSEP hashes
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from vlep.api.deps import AuthPrincipal, get_db, require_role

router = APIRouter(prefix="/system", tags=["System Diagnostics"])
logger = logging.getLogger(__name__)

@router.get(
    "/gordon/health",
    summary="Gordon Diagnostic Healthcheck",
    description="Provides real-time system metrics for Docker CLI AI analysis.",
)
async def gordon_healthcheck(
    db: AsyncSession = Depends(get_db),
    # In production, require a dedicated service account role for Gordon
    _: AuthPrincipal = Depends(require_role("admin")),
) -> dict[str, Any]:
    # Check DB latency
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"degraded: {e}"

    # Return structured JSON for Gordon
    return {
        "status": "online",
        "orchestrator_version": "v1.0.0",
        "database": db_status,
        "recommendations": [
            "Check /gordon/queues if NLP latency > 500ms"
        ]
    }

@router.get(
    "/gordon/queues",
    summary="Celery Queue Depth & Latency",
)
async def gordon_queues(
    _: AuthPrincipal = Depends(require_role("admin")),
) -> dict[str, Any]:
    # Placeholder for actual Redis/Celery queue depth query
    return {
        "gpu_heavy_queue_depth": 0,
        "io_bound_queue_depth": 0,
        "estimated_nlp_latency_ms": 120,
        "workers_active": {
            "gpu": 1,
            "io": 4
        }
    }

@router.post(
    "/gordon/ledger/verify",
    summary="Verify CSEP Hash Integrity",
)
async def verify_ledger(
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Scans all CSEP profiles and re-computes hashes to ensure no tampering."""
    from sqlalchemy import select
    from vlep.models.csep import CSEPProfile
    from vlep.services.csep_resolver import CsepResolverService
    
    result = await db.execute(select(CSEPProfile))
    profiles = result.scalars().all()
    
    mismatches = []
    for profile in profiles:
        expected_hash = CsepResolverService.calculate_profile_hash(profile)
        if profile.profile_hash != expected_hash:
            mismatches.append(str(profile.csep_id))
            
    return {
        "status": "verified" if not mismatches else "tampering_detected",
        "profiles_scanned": len(profiles),
        "tampering_detected": len(mismatches) > 0,
        "mismatched_csep_ids": mismatches
    }
