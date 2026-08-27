"""
VLEP Pipeline — Shared FastAPI Dependencies.

Provides:
  - ``get_db``  : async DB session per request (injected via Depends)
  - ``get_principal`` : parsed auth principal from the request state
  - ``require_role``  : role-based access control factory
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.db import AsyncSessionLocal

# ── Database session dependency ──────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a per-request async SQLAlchemy session.

    The session is automatically committed on success or rolled back on any
    unhandled exception; it is always closed when the request finishes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Auth principal dependency ────────────────────────────────────────────────

class AuthPrincipal:
    """Parsed identity of the authenticated caller.

    In production this would be populated by the OIDC/JWT middleware; in the
    current stub it is extracted from custom request headers so that the
    governance audit middleware and the routers can share a consistent principal
    without duplicating header parsing.
    """

    def __init__(
        self,
        actor_id: str,
        actor_role: str,
        access_reason: str,
        is_authenticated: bool = True,
    ) -> None:
        self.actor_id = actor_id
        self.actor_role = actor_role
        self.access_reason = access_reason
        self.is_authenticated = is_authenticated

    def __repr__(self) -> str:  # pragma: no cover
        return f"AuthPrincipal(actor_id={self.actor_id!r}, role={self.actor_role!r})"


def get_principal(request: Request) -> AuthPrincipal:
    """Extract the caller identity from the request.

    Production note: replace this stub with real OIDC JWT validation.
    The middleware (``vlep/api/middleware/auth.py``) will populate
    ``request.state.principal`` once real auth is wired in.
    """
    # If auth middleware has already populated the principal, return it.
    if hasattr(request.state, "principal") and request.state.principal is not None:
        return request.state.principal

    # Dev / test fallback: read from headers supplied by the caller.
    actor_id = request.headers.get("X-Actor-ID", "anonymous")
    actor_role = request.headers.get("X-Actor-Role", "readonly")
    access_reason = request.headers.get("X-Access-Reason", "unspecified")
    return AuthPrincipal(
        actor_id=actor_id,
        actor_role=actor_role,
        access_reason=access_reason,
        is_authenticated=(actor_id != "anonymous"),
    )


# ── Role-based access control helper ────────────────────────────────────────

ROLE_HIERARCHY: dict[str, int] = {
    "readonly": 0,
    "clinic_nurse": 1,
    "clinician": 2,
    "epileptologist": 3,
    "clinical_director": 4,
    "admin": 5,
    "system": 99,
}


def require_role(minimum_role: str):
    """FastAPI dependency factory: raise 403 if the caller's role is insufficient.

    Usage::

        @router.delete("/{patient_id}")
        async def delete_patient(
            principal: AuthPrincipal = Depends(require_role("admin")),
        ): ...
    """
    required_level = ROLE_HIERARCHY.get(minimum_role, 999)

    def _check(principal: AuthPrincipal = Depends(get_principal)) -> AuthPrincipal:
        caller_level = ROLE_HIERARCHY.get(principal.actor_role, -1)
        if caller_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient role. Required: '{minimum_role}', "
                    f"caller role: '{principal.actor_role}'."
                ),
            )
        return principal

    return _check
