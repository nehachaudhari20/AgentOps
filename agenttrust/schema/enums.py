"""Enumerations and constants for AgentTrust Phase 2.1 schemas."""

from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "2.1.0"


class NodeKind(str, Enum):
    EVENT = "EVENT"
    ARTIFACT = "ARTIFACT"


class EventCategory(str, Enum):
    """Conceptual execution categories (not temporal ranks)."""

    INSTRUCTION = "instruction"
    REASONING = "reasoning"
    RETRIEVAL = "retrieval"
    KNOWLEDGE = "knowledge"
    TRANSFORMATION = "transformation"
    TOOL = "tool"
    DECISION = "decision"
    OTHER = "other"


class EventStatus(str, Enum):
    """
    Extensible status vocabulary.

    ``unknown`` records that status was not observed — it does not mean success.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class RelationshipType(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    INVOKES = "INVOKES"
    RETRIES = "RETRIES"
    OBSERVED_AFTER = "OBSERVED_AFTER"


# Known legacy / common event_type → category. Unknown types map to OTHER.
_EVENT_TYPE_TO_CATEGORY: dict[str, EventCategory] = {
    "prompt": EventCategory.INSTRUCTION,
    "reasoning": EventCategory.REASONING,
    "retrieval": EventCategory.RETRIEVAL,
    "document": EventCategory.KNOWLEDGE,
    "embedding": EventCategory.TRANSFORMATION,
    "tool_call": EventCategory.TOOL,
    "action": EventCategory.DECISION,
}


def category_for_event_type(event_type: str) -> EventCategory:
    """Map an event_type string to a category; unknown → OTHER."""
    key = (event_type or "").strip().lower()
    return _EVENT_TYPE_TO_CATEGORY.get(key, EventCategory.OTHER)
