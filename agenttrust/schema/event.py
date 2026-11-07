"""Event record schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from agenttrust.schema.enums import EventCategory, EventStatus, SCHEMA_VERSION


def parse_timestamp(value: Any, *, field_name: str) -> datetime:
    """
    Parse a timestamp into a timezone-aware UTC datetime.

    Accepts ISO 8601 strings (with Z or offset) or numeric Unix seconds.
    Raises ValueError on malformed values.
    """
    if value is None:
        raise ValueError(f"{field_name} is missing")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} is empty")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} is not a valid ISO 8601 timestamp: {value!r}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise ValueError(f"{field_name} has unsupported type {type(value).__name__}")


def format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO 8601 UTC with Z suffix."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EventRecord:
    """Validated observable execution event (Phase 2.1 core schema)."""

    event_id: str
    trace_id: str
    event_type: str
    category: EventCategory
    agent_id: Optional[str]
    status: EventStatus
    ts_start: Optional[datetime]
    ts_end: Optional[datetime]
    input_artifact_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    dependency_event_ids: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    # Explicit optional relationship hints (only when source evidence provides them)
    invokes_event_ids: tuple[str, ...] = ()
    retries_event_id: Optional[str] = None
    observed_after_event_ids: tuple[str, ...] = ()
    # Optional accountability identities (absent ⇒ unobserved; never inferred)
    model_id: Optional[str] = None
    tool_id: Optional[str] = None
    # Non-sensitive key/value tags only (e.g. subtype=memory). Historical records omit this.
    metadata: tuple[tuple[str, str], ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        """Serializable view without inventing fields."""
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "category": self.category.value,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "ts_start": format_timestamp(self.ts_start),
            "ts_end": format_timestamp(self.ts_end),
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_ids": list(self.output_artifact_ids),
            "dependency_event_ids": list(self.dependency_event_ids),
            "schema_version": self.schema_version,
            "invokes_event_ids": list(self.invokes_event_ids),
            "retries_event_id": self.retries_event_id,
            "observed_after_event_ids": list(self.observed_after_event_ids),
            "model_id": self.model_id,
            "tool_id": self.tool_id,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def normalize_id_list(values: Any, *, field_name: str) -> tuple[str, ...]:
        if values is None:
            return ()
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"{field_name} must be a list of strings")
        out: list[str] = []
        seen: set[str] = set()
        for item in values:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{field_name} contains an invalid id: {item!r}")
            eid = item.strip()
            if eid not in seen:
                seen.add(eid)
                out.append(eid)
        return tuple(out)
