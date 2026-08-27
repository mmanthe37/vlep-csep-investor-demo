"""
VLEP Pipeline — Authentication Middleware Stub.

This module provides the auth middleware skeleton that would be replaced with
real OIDC/JWT validation in production.  Currently it:

1. Reads ``Authorization: Bearer <token>`` from every incoming request.
2. Validates the token structure (stub — accepts any non-empty token).
3. Populates ``request.state.principal`` with an ``AuthPrincipal`` so that
   downstream dependencies (``deps.get_principal``) can read it without
   duplicating header parsing.
4. Allows unauthenticated requests through with an ``anonymous`` principal so
   that development endpoints are reachable without a token.

Production replacement checklist:
  - Install ``python-jose`` or ``authlib``
  - Set ``OIDC_ISSUER_URL``, ``OIDC_CLIENT_ID``, ``OIDC_AUDIENCE`` in ``.env``
  - Fetch JWKS from ``{issuer}/.well-known/jwks.json``
  - Decode and verify the JWT with the public key
  - Map ``sub`` → ``actor_id``, custom claim ``role`` → ``actor_role``
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from vlep.api.deps import AuthPrincipal

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """OIDC/JWT Authentication Middleware (stub implementation).

    In production wire ``_validate_token`` to your OIDC provider.
    """

    # Paths that are always public (no auth required)
    PUBLIC_PATHS: frozenset[str] = frozenset({
        "/",
        "/health",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    })

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.PUBLIC_PATHS:
            request.state.principal = None
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        principal = self._resolve_principal(auth_header, request)
        request.state.principal = principal

        if not principal.is_authenticated:
            logger.debug("Unauthenticated request to %s — anonymous principal set", request.url.path)

        return await call_next(request)

    # ── Token resolution ─────────────────────────────────────────────────────

    def _resolve_principal(self, auth_header: str, request: Request) -> AuthPrincipal:
        """Parse ``Authorization`` header and return an ``AuthPrincipal``.

        Stub: any ``Bearer <non-empty>`` token is accepted. Replace with real
        JWT validation before production.
        """
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
            if token:
                return self._validate_token(token, request)

        # Fallback: read dev headers (mirrors deps.get_principal logic)
        actor_id = request.headers.get("X-Actor-ID", "anonymous")
        actor_role = request.headers.get("X-Actor-Role", "readonly")
        access_reason = request.headers.get("X-Access-Reason", "unspecified")
        return AuthPrincipal(
            actor_id=actor_id,
            actor_role=actor_role,
            access_reason=access_reason,
            is_authenticated=(actor_id != "anonymous"),
        )

    @staticmethod
    def _validate_token(token: str, request: Request) -> AuthPrincipal:
        """Stub JWT validator — accepts any non-empty bearer token.

        TODO: Replace with:
            1. JWKS fetch from ``{OIDC_ISSUER_URL}/.well-known/jwks.json``
            2. ``jose.jwt.decode(token, jwks, audience=OIDC_AUDIENCE)``
            3. Extract ``sub``, ``role``, ``reason`` from claims
        """
        # Dev stub: decode fake token as "actor_id:role:reason"
        try:
            parts = token.split(":")
            actor_id = parts[0] if len(parts) > 0 else "dev_user"
            actor_role = parts[1] if len(parts) > 1 else "clinician"
            access_reason = parts[2] if len(parts) > 2 else "api_access"
            return AuthPrincipal(
                actor_id=actor_id,
                actor_role=actor_role,
                access_reason=access_reason,
                is_authenticated=True,
            )
        except Exception:
            logger.warning("Token parsing failed; falling back to anonymous principal")
            return AuthPrincipal(
                actor_id="anonymous",
                actor_role="readonly",
                access_reason="unspecified",
                is_authenticated=False,
            )
