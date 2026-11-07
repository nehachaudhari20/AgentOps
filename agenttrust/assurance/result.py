"""Assurance Profile result structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agenttrust.assurance.models import (
    ASSURANCE_ALGORITHM_NAME,
    ASSURANCE_ALGORITHM_VERSION,
    AssuranceStatus,
    worst_status,
)


@dataclass
class DimensionResult:
    dimension_id: str
    status: AssuranceStatus
    value: Any = None
    evidence_refs: list[str] = field(default_factory=list)
    rule_id: str = ""
    warnings: list[str] = field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "status": self.status.value,
            "value": self.value,
            "evidence_refs": list(self.evidence_refs),
            "rule_id": self.rule_id,
            "warnings": list(self.warnings),
            "explanation": self.explanation,
            "limitations": list(self.limitations),
        }


@dataclass
class AssuranceProfile:
    """
    Evidence-bounded multi-dimension assurance assessment for one analysis context.

    Not a trust score, causal verdict, or legal responsibility claim.
    """

    algorithm_name: str = ASSURANCE_ALGORITHM_NAME
    algorithm_version: str = ASSURANCE_ALGORITHM_VERSION
    outcome_id: Optional[str] = None
    projection_kind: Optional[str] = None
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    overall_status: AssuranceStatus = AssuranceStatus.UNAVAILABLE
    warnings: list[str] = field(default_factory=list)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    disclaimer: str = (
        "Assurance Profile reports evidence availability and structural consistency only. "
        "It does not measure agent trustworthiness, reconstruct hidden reasoning, or prove "
        "causal or legal responsibility."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_name": self.algorithm_name,
            "algorithm_version": self.algorithm_version,
            "outcome_id": self.outcome_id,
            "projection_kind": self.projection_kind,
            "overall_status": self.overall_status.value,
            "dimensions": {k: v.to_dict() for k, v in sorted(self.dimensions.items())},
            "warnings": list(self.warnings),
            "reproducibility": dict(self.reproducibility),
            "disclaimer": self.disclaimer,
        }

    @staticmethod
    def compute_overall(dimensions: dict[str, DimensionResult]) -> AssuranceStatus:
        return worst_status([d.status for d in dimensions.values()])
