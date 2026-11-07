"""Benchmark configuration, scale tiers, and trace manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

GENERATOR_VERSION = "2.5.1"


class ScaleTier(str, Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


SCALE_SPECS: dict[ScaleTier, dict[str, int]] = {
    ScaleTier.S1: {"agents": 5, "target_events": 50},
    ScaleTier.S2: {"agents": 10, "target_events": 100},
    ScaleTier.S3: {"agents": 20, "target_events": 250},
    ScaleTier.S4: {"agents": 50, "target_events": 500},
    ScaleTier.S5: {"agents": 50, "target_events": 1000},
}


class TopologyId(str, Enum):
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"
    PARALLEL_FAN = "parallel_fanout_fanin"
    SHARED_ARTIFACT = "shared_artifact"
    DELEGATED = "delegated_multi_agent"
    MIXED = "mixed_realistic"


class ScenarioId(str, Enum):
    FINANCIAL_LOAN = "financial_loan"
    FRAUD_INVESTIGATION = "fraud_investigation"
    COMPLIANCE_REVIEW = "compliance_review"
    RESEARCH_SYNTHESIS = "research_synthesis"
    TRANSACTION_EXECUTION = "transaction_execution"


@dataclass(frozen=True)
class BenchmarkConfig:
    """Fully specified generation request (deterministic under seed)."""

    scenario_id: ScenarioId
    topology_id: TopologyId
    scale_tier: ScaleTier
    seed: int
    fault_types: tuple[str, ...] = ()
    incomplete: bool = False
    generator_version: str = GENERATOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id.value,
            "topology_id": self.topology_id.value,
            "scale_tier": self.scale_tier.value,
            "seed": int(self.seed),
            "fault_types": list(self.fault_types),
            "incomplete": bool(self.incomplete),
            "generator_version": self.generator_version,
            "target_agents": SCALE_SPECS[self.scale_tier]["agents"],
            "target_events": SCALE_SPECS[self.scale_tier]["target_events"],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def make_trace_id(self) -> str:
        faults = "-".join(self.fault_types) if self.fault_types else "clean"
        incomplete = "inc" if self.incomplete else "cmp"
        # Compact, filesystem-safe, deterministic
        return (
            f"bench-{self.scenario_id.value}-{self.topology_id.value}-"
            f"{self.scale_tier.value}-s{self.seed}-{faults}-{incomplete}"
        )


@dataclass
class TraceManifest:
    """Reproducibility metadata for one generated trace."""

    trace_id: str
    scenario_id: str
    topology_id: str
    scale_tier: str
    seed: int
    generator_version: str
    config_fingerprint: str
    expected_event_count: int
    actual_event_count: int
    agent_count: int
    artifact_count: int
    intervention_count: int
    outcome_event_ids: list[str] = field(default_factory=list)
    incomplete: bool = False
    fault_types: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceManifest":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def config_fingerprint(config: BenchmarkConfig) -> str:
    return config.fingerprint()
