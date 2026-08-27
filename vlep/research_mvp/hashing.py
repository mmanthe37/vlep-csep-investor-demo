"""Canonical hashing and append-only chain verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


def canonical_json(value: Any) -> str:
    """Return a stable JSON representation suitable for reproducible hashes."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_json(value: Any) -> str:
    """Hash a JSON-compatible value using canonical serialization."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def ledger_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable fields covered by a ledger event hash."""

    return {
        key: value
        for key, value in event.items()
        if key not in {"hash_prev", "hash_self", "integrity"}
    }


def calculate_ledger_hash(event: Mapping[str, Any], hash_prev: str) -> str:
    """Calculate an event hash chained to the previous event."""

    return sha256_json({"hash_prev": hash_prev, "event": ledger_payload(event)})


def verify_ledger_chain(events: Iterable[Mapping[str, Any]]) -> bool:
    """Verify sequence order, prior links, and every event digest."""

    previous = "GENESIS"
    expected_sequence = 1
    for event in events:
        if int(event["seq"]) != expected_sequence:
            return False
        if event.get("hash_prev") != previous:
            return False
        expected_hash = calculate_ledger_hash(event, previous)
        if event.get("hash_self") != expected_hash:
            return False
        previous = expected_hash
        expected_sequence += 1
    return True
