"""Typed relationship records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from agenttrust.schema.enums import RelationshipType


@dataclass(frozen=True)
class RelationshipRecord:
    """
    Directed typed provenance relationship.

    Semantics (source → target):
    - DEPENDS_ON: upstream event → dependent event
    - PRODUCES: event → artifact
    - CONSUMES: artifact → event
    - INVOKES: caller event → callee event
    - RETRIES: retrying event → original event
    - OBSERVED_AFTER: earlier event → later event (temporal only; not causal)
    """

    rel_type: RelationshipType
    source_id: str
    target_id: str
    derived: bool = False
    evidence: Optional[str] = None

    def edge_key(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.rel_type.value)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "rel_type": self.rel_type.value,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "derived": self.derived,
            "evidence": self.evidence,
        }
