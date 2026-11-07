"""Typed MFAV result structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agenttrust.accountability.taxonomy import FACTOR_ORDER, MFAVFactor


class MFAVStatus(str, Enum):
    """Normalization / completeness status for an MFAV profile."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    OVERRIDDEN = "overridden"
    ZERO_ALLOCATION = "zero_allocation"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class EntityContribution:
    """Allocation counted once under a primary factor for one stable entity id."""

    factor: str
    entity_id: str
    entity_kind: str
    allocation: float
    unidentified: bool
    event_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "allocation": self.allocation,
            "unidentified": self.unidentified,
            "event_ids": list(self.event_ids),
        }


@dataclass(frozen=True)
class EventAssignment:
    """Per-event exclusive factor assignment with raw RPA allocation."""

    event_id: str
    factor: str
    allocation: float
    entity_id: str
    entity_kind: str
    unidentified: bool
    secondary_subtypes: tuple[str, ...] = ()
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "factor": self.factor,
            "allocation": self.allocation,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "unidentified": self.unidentified,
            "secondary_subtypes": list(self.secondary_subtypes),
            "rationale": self.rationale,
        }


@dataclass
class MFAVResult:
    """
    Evidence-bounded accountability profile for one RPA outcome.

    Describes how RPA structural allocation is distributed across exclusive
    factors. Not legal liability, causal proof, fault probability, or trust.
    """

    outcome_id: str
    projection_kind: str
    rpa_algorithm_name: str
    rpa_algorithm_version: str
    rpa_alpha: float
    parent_allocation_policy: str
    mfav_algorithm_name: str
    mfav_algorithm_version: str
    taxonomy_version: str
    mapping_policy: str
    raw_factor_allocations: dict[str, float]
    normalized_factor_vector: Optional[dict[str, float]]
    total_raw_allocation: float
    conservation_error: float
    status: MFAVStatus
    complete: bool
    entity_contributions: list[EntityContribution]
    event_assignments: list[EventAssignment]
    secondary_subtype_totals: dict[str, float]
    unidentified_contributions: list[EntityContribution]
    classification_warnings: list[str] = field(default_factory=list)
    rpa_warnings: list[str] = field(default_factory=list)
    overridden_guards: list[str] = field(default_factory=list)
    rpa_completeness: dict[str, Any] = field(default_factory=dict)
    reproducibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "projection_kind": self.projection_kind,
            "rpa_algorithm_name": self.rpa_algorithm_name,
            "rpa_algorithm_version": self.rpa_algorithm_version,
            "rpa_alpha": self.rpa_alpha,
            "parent_allocation_policy": self.parent_allocation_policy,
            "mfav_algorithm_name": self.mfav_algorithm_name,
            "mfav_algorithm_version": self.mfav_algorithm_version,
            "taxonomy_version": self.taxonomy_version,
            "mapping_policy": self.mapping_policy,
            "raw_factor_allocations": {
                f.value: float(self.raw_factor_allocations.get(f.value, 0.0))
                for f in FACTOR_ORDER
            },
            "normalized_factor_vector": (
                None
                if self.normalized_factor_vector is None
                else {
                    f.value: float(self.normalized_factor_vector.get(f.value, 0.0))
                    for f in FACTOR_ORDER
                }
            ),
            "total_raw_allocation": self.total_raw_allocation,
            "conservation_error": self.conservation_error,
            "status": self.status.value,
            "complete": self.complete,
            "entity_contributions": [e.to_dict() for e in self.entity_contributions],
            "event_assignments": [a.to_dict() for a in self.event_assignments],
            "secondary_subtype_totals": dict(self.secondary_subtype_totals),
            "unidentified_contributions": [e.to_dict() for e in self.unidentified_contributions],
            "classification_warnings": list(self.classification_warnings),
            "rpa_warnings": list(self.rpa_warnings),
            "overridden_guards": list(self.overridden_guards),
            "rpa_completeness": dict(self.rpa_completeness),
            "reproducibility": dict(self.reproducibility),
        }

    @staticmethod
    def empty_factor_map() -> dict[str, float]:
        return {f.value: 0.0 for f in MFAVFactor}
