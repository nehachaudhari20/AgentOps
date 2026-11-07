"""Versioned comparison / evaluation result contracts (Phase 2.10–2.11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

COMPARISON_FORMAT_VERSION = "agenttrust-comparison-result-v1"
METRIC_FORMAT_VERSION = "agenttrust-metric-result-v1"


@dataclass
class AllocationResult:
    method_id: str
    method_version: str
    information_budget: str  # online_evidence | offline_combinatorial | alias
    trace_id: str
    outcome_id: str
    projection_kind: Optional[str]
    agent_allocations: dict[str, float]
    status: str  # ok | undefined | ineligible | failed
    eligibility: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reproducibility: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": COMPARISON_FORMAT_VERSION,
            "method_id": self.method_id,
            "method_version": self.method_version,
            "information_budget": self.information_budget,
            "trace_id": self.trace_id,
            "outcome_id": self.outcome_id,
            "projection_kind": self.projection_kind,
            "agent_allocations": dict(self.agent_allocations),
            "status": self.status,
            "eligibility": dict(self.eligibility),
            "config": dict(self.config),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "reproducibility": dict(self.reproducibility),
        }


def normalize_agent_vector(raw: dict[str, float]) -> tuple[dict[str, float], str]:
    """Return non-negative normalized vector summing to 1, or empty + undefined."""
    cleaned = {k: float(v) for k, v in raw.items() if v is not None}
    for k, v in cleaned.items():
        if v < -1e-15 or v != v:  # NaN/neg
            return {}, "undefined"
    pos = {k: max(0.0, v) for k, v in cleaned.items()}
    s = sum(pos.values())
    if s <= 0.0:
        return {}, "undefined"
    return {k: v / s for k, v in sorted(pos.items())}, "ok"
