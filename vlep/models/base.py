"""
VLEP ORM — Declarative Base & shared mixins.

Every model inherits from ``Base``.  Common audit columns are provided by
``TimestampMixin`` and ``UUIDPrimaryKeyMixin``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all VLEP ORM models."""

    pass


class UUIDPrimaryKeyMixin:
    """Mixin that adds a UUID primary key with server-side default."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Mixin that adds created_at with server-side default."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
