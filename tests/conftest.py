"""Shared pytest fixtures for AgentTrust Phase 2.1 tests."""

from __future__ import annotations

import hashlib
from typing import Any


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_artifact(aid: str, content: str = "x", atype: str = "blob") -> dict[str, Any]:
    return {
        "artifact_id": aid,
        "artifact_type": atype,
        "content_hash": f"sha256:{sha256_hex(content)}",
        "schema_version": "2.1.0",
    }


def make_event(
    event_id: str,
    *,
    event_type: str = "reasoning",
    category: str | None = None,
    agent_id: str | None = "AgentA",
    status: str = "success",
    deps: list[str] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    ts_start: str = "2024-01-01T00:00:00Z",
    ts_end: str | None = "2024-01-01T00:00:01Z",
    trace_id: str = "trace-test",
    **extra: Any,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "event_id": event_id,
        "trace_id": trace_id,
        "event_type": event_type,
        "agent_id": agent_id,
        "status": status,
        "ts_start": ts_start,
        "dependency_event_ids": deps or [],
        "input_artifact_ids": inputs or [],
        "output_artifact_ids": outputs or [],
        "schema_version": "2.1.0",
    }
    if category is not None:
        rec["category"] = category
    if ts_end is not None:
        rec["ts_end"] = ts_end
    rec.update(extra)
    return rec
