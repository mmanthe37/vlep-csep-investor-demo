"""
FastAPI Middleware for HIPAA-compliant Access Logging.

Captures all patient-level data accesses and writes to governance.access_logs.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from vlep.db import AsyncSessionLocal
from vlep.models.governance import AccessLog

logger = logging.getLogger(__name__)

# Pattern to extract UUIDs from request path
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class GovernanceAuditMiddleware(BaseHTTPMiddleware):
    """Middleware to audit log patient data accesses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Proceed with the request
        response = await call_next(request)

        # 2. Audit log after request completes (or if it succeeds)
        # We target requests that read/write data in core, evidence, phenotyping, modeling, csep schemas.
        path = request.url.path
        is_patient_data = any(
            segment in path
            for segment in ["patients", "evidence", "ledger", "phenotypes", "assertions", "csep", "profiles", "modeling", "predictions"]
        )

        if is_patient_data:
            try:
                # Extract headers or default
                actor_id = request.headers.get("X-Actor-ID", "system_user")
                actor_role = request.headers.get("X-Actor-Role", "clinician")
                access_reason = request.headers.get("X-Access-Reason", "clinical_review")

                # Check for patient ID in query params, headers, or extract from path
                patient_id_str = request.headers.get("X-Patient-ID")
                if not patient_id_str:
                    patient_id_str = request.query_params.get("patient_id")
                if not patient_id_str:
                    # Find first UUID in path
                    match = UUID_PATTERN.search(path)
                    if match:
                        patient_id_str = match.group(0)

                patient_id = None
                if patient_id_str:
                    try:
                        patient_id = uuid.UUID(patient_id_str)
                    except ValueError:
                        pass

                action = f"{request.method} {path}"
                ip_address = request.client.host if request.client else "127.0.0.1"
                user_agent = request.headers.get("user-agent", "unknown")

                # Map resource details
                resource_schema = None
                resource_table = None
                if "patients" in path:
                    resource_schema = "core"
                    resource_table = "patients"
                elif "evidence" in path or "ledger" in path:
                    resource_schema = "evidence"
                    resource_table = "ledger_events"
                elif "phenotypes" in path or "assertions" in path:
                    resource_schema = "phenotyping"
                    resource_table = "phenotype_assertions"
                elif "csep" in path or "profiles" in path:
                    resource_schema = "csep"
                    resource_table = "profiles"
                elif "modeling" in path or "predictions" in path:
                    resource_schema = "modeling"
                    resource_table = "predictions"

                # Log to DB asynchronously in an isolated session
                async with AsyncSessionLocal() as session:
                    log_entry = AccessLog(
                        actor_id=actor_id,
                        actor_role=actor_role,
                        action=action,
                        resource_schema=resource_schema,
                        resource_table=resource_table,
                        patient_id=patient_id,
                        access_reason=access_reason,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        metadata_={
                            "query_params": dict(request.query_params),
                            "status_code": response.status_code,
                        }
                    )
                    session.add(log_entry)
                    await session.commit()
                    logger.debug("Logged patient data access by %s on %s", actor_id, path)

            except Exception as e:
                logger.error("Audit log failed: %s", e)

        return response
