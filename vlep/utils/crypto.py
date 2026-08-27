"""
Cryptographic utility functions for the VLEP Evidence Ledger.
Provides SHA-256 hash generation and chain verification.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.evidence import LedgerEvent


def format_postgres_timestamp(dt: datetime) -> str:
    """Format a datetime in the standard PostgreSQL timestamptz text representation.
    
    PostgreSQL text representation of timestamptz looks like: '2026-06-24 22:11:35.123456+00'
    or '2026-06-24 22:11:35+00'.
    """
    # Convert to UTC first
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt_utc = dt
    else:
        dt_utc = dt.astimezone(UTC)

    # Format to YYYY-MM-DD HH:MM:SS
    base = dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    if dt_utc.microsecond > 0:
        base += f".{dt_utc.microsecond:06d}"

    # In PostgreSQL, UTC timezone is printed as +00
    return f"{base}+00"


def format_postgres_json(val: Any) -> str:
    """Format a JSON object/list in the standard PostgreSQL JSONB text representation.
    
    SQLAlchemy/asyncpg inputs JSONB as JSON strings. PostgreSQL sorts keys and removes
    unnecessary spaces when returning JSONB ::text.
    In VLEP, we use standard json.dumps with sort_keys=True and no spacing inside delimiters,
    matching PostgreSQL's default serialization.
    """
    if val is None:
        return ""
    # PostgreSQL jsonb serialization: compact, key-sorted
    return json.dumps(val, separators=(",", ":"), sort_keys=True)


def calculate_event_hash(event_data: dict[str, Any], hash_prev: str | None = None) -> str:
    """Calculate the SHA-256 hash of a ledger event payload in Python.
    
    This matches the logic defined in evidence.set_ledger_event_hash().
    """
    # Helper to convert to str or empty string
    def clean_str(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, uuid.UUID):
            return str(val)
        if isinstance(val, datetime):
            return format_postgres_timestamp(val)
        if isinstance(val, (dict, list)):
            return format_postgres_json(val)
        return str(val)

    # Get data element and normalized codes
    data_element_str = format_postgres_json(event_data.get("data_element"))
    normalized_codes_str = format_postgres_json(event_data.get("normalized_codes") or [])

    parts = [
        hash_prev or "",
        clean_str(event_data.get("event_id")),
        clean_str(event_data.get("patient_id")),
        clean_str(event_data.get("observed_at")),
        clean_str(event_data.get("ingested_at")),
        clean_str(event_data.get("domain")),
        data_element_str,
        normalized_codes_str,
        clean_str(event_data.get("source_attribution")),
        clean_str(event_data.get("source_system_id")),
        clean_str(event_data.get("raw_resource_id")),
        clean_str(event_data.get("source_document_id")),
        clean_str(event_data.get("source_claim_id")),
        format_postgres_json(event_data.get("provenance") or {}),
        f"{float(event_data.get('certainty_level', 1.0)):.4f}",  # numeric(5,4)
        clean_str(event_data.get("validation_status", "raw")),
        clean_str(event_data.get("nosology_version_id")),
        clean_str(event_data.get("supersedes_event_id")),
    ]

    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def verify_ledger_chain(session: AsyncSession) -> bool:
    """Verify the integrity of the evidence ledger hash chain.
    
    Performs two checks:
    1. Chronological linkage: event[i].hash_prev == event[i-1].hash_self
    2. SQL-side re-computation of each hash to check against tamper-evidence.
    
    Returns True if valid, raises ValueError if a validation error occurs.
    """
    # 1. Fetch all events ordered by event_seq
    stmt = select(LedgerEvent).order_by(LedgerEvent.event_seq)
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    if not events:
        return True

    # Check linkage
    for i in range(1, len(events)):
        prev_event = events[i - 1]
        curr_event = events[i]

        if curr_event.hash_prev != prev_event.hash_self:
            raise ValueError(
                f"Ledger linkage broken at event_seq {curr_event.event_seq}. "
                f"Expected hash_prev '{prev_event.hash_self}', got '{curr_event.hash_prev}'"
            )

    # 2. Check digest verification via SQL to verify hash correctness against actual DB state
    query = text("""
        SELECT event_seq, hash_self,
        encode(digest(
          coalesce(hash_prev, '') || '|' ||
          event_id::text || '|' ||
          coalesce(patient_id::text, '') || '|' ||
          observed_at::text || '|' ||
          ingested_at::text || '|' ||
          domain::text || '|' ||
          data_element::text || '|' ||
          normalized_codes::text || '|' ||
          source_attribution::text || '|' ||
          coalesce(source_system_id::text, '') || '|' ||
          coalesce(raw_resource_id::text, '') || '|' ||
          coalesce(source_document_id::text, '') || '|' ||
          coalesce(source_claim_id::text, '') || '|' ||
          provenance::text || '|' ||
          certainty_level::text || '|' ||
          validation_status::text || '|' ||
          coalesce(nosology_version_id::text, '') || '|' ||
          coalesce(supersedes_event_id::text, ''),
          'sha256'
        ), 'hex') AS computed_hash
        FROM evidence.ledger_events
        ORDER BY event_seq;
    """)

    res = await session.execute(query)
    for row in res:
        seq = row[0]
        recorded = row[1]
        computed = row[2]
        if recorded != computed:
            raise ValueError(
                f"Ledger tamper check failed at event_seq {seq}. "
                f"Recorded hash '{recorded}', computed from fields '{computed}'"
            )

    return True
