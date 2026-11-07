"""
Benchmark ground truth — stored separately from algorithm inputs.

Never embed answer labels in ordinary event metadata used by RPA/MFAV.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agenttrust.benchmark.faults import InterventionRecord


@dataclass
class LineageGroundTruth:
    event_dependencies: dict[str, list[str]] = field(default_factory=dict)
    artifact_producers: dict[str, str] = field(default_factory=dict)  # artifact -> event
    artifact_consumers: dict[str, list[str]] = field(default_factory=dict)  # artifact -> events
    invocations: dict[str, list[str]] = field(default_factory=dict)  # caller -> callees
    retries: dict[str, str] = field(default_factory=dict)  # retry_event -> prior
    expected_relationships: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructuralGroundTruth:
    agent_ids: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    event_categories: dict[str, str] = field(default_factory=dict)
    topology_id: str = ""
    scenario_id: str = ""
    outcome_event_ids: list[str] = field(default_factory=list)
    scale_tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceQualityGroundTruth:
    intentionally_incomplete: bool = False
    missing_event_ids: list[str] = field(default_factory=list)
    missing_dependency_refs: list[str] = field(default_factory=list)
    corrupted_artifact_ids: list[str] = field(default_factory=list)
    incomplete_observation_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkGroundTruth:
    """Full ground-truth package for one generated trace."""

    trace_id: str
    generator_version: str
    seed: int
    lineage: LineageGroundTruth = field(default_factory=LineageGroundTruth)
    interventions: list[InterventionRecord] = field(default_factory=list)
    structural: StructuralGroundTruth = field(default_factory=StructuralGroundTruth)
    quality: TraceQualityGroundTruth = field(default_factory=TraceQualityGroundTruth)
    ground_truth_version: str = "gt-2.5.1"
    attribution_reference: Any = None  # AttributionReferenceGT | dict | None (Phase 2.9)
    disclaimer: str = (
        "Ground truth records generator intent only. "
        "Graph reachability is not causal proof. "
        "Do not feed these labels into RPA/MFAV algorithm inputs. "
        "Attribution reference (if present) is equal-root structural share, not causal GT."
    )

    def to_dict(self) -> dict[str, Any]:
        attr = self.attribution_reference
        if attr is not None and hasattr(attr, "to_dict"):
            attr = attr.to_dict()
        return {
            "trace_id": self.trace_id,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "ground_truth_version": self.ground_truth_version,
            "disclaimer": self.disclaimer,
            "lineage": self.lineage.to_dict(),
            "interventions": [i.to_dict() for i in self.interventions],
            "structural": self.structural.to_dict(),
            "quality": self.quality.to_dict(),
            "attribution_reference": attr,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkGroundTruth":
        lineage = LineageGroundTruth(**data.get("lineage", {}))
        structural = StructuralGroundTruth(**data.get("structural", {}))
        quality = TraceQualityGroundTruth(**data.get("quality", {}))
        interventions = [InterventionRecord.from_dict(i) for i in data.get("interventions", [])]
        return cls(
            trace_id=data["trace_id"],
            generator_version=data.get("generator_version", ""),
            seed=int(data.get("seed", 0)),
            lineage=lineage,
            interventions=interventions,
            structural=structural,
            quality=quality,
            ground_truth_version=data.get("ground_truth_version", "gt-2.5.1"),
            attribution_reference=data.get("attribution_reference"),
            disclaimer=data.get("disclaimer", ""),
        )


def build_lineage_from_events(events: list[dict[str, Any]]) -> LineageGroundTruth:
    """Capture lineage as emitted (post-fault), for consistency checks."""
    lineage = LineageGroundTruth()
    producers: dict[str, str] = {}
    consumers: dict[str, list[str]] = {}
    for ev in events:
        eid = ev["event_id"]
        deps = list(ev.get("dependency_event_ids") or [])
        lineage.event_dependencies[eid] = deps
        for aid in ev.get("output_artifact_ids") or []:
            producers[aid] = eid
            lineage.expected_relationships.append(
                {"rel_type": "PRODUCES", "source_id": eid, "target_id": aid}
            )
        for aid in ev.get("input_artifact_ids") or []:
            consumers.setdefault(aid, []).append(eid)
            lineage.expected_relationships.append(
                {"rel_type": "CONSUMES", "source_id": aid, "target_id": eid}
            )
        for dep in deps:
            lineage.expected_relationships.append(
                {"rel_type": "DEPENDS_ON", "source_id": dep, "target_id": eid}
            )
        invokes = list(ev.get("invokes_event_ids") or [])
        if invokes:
            lineage.invocations[eid] = invokes
            for callee in invokes:
                lineage.expected_relationships.append(
                    {"rel_type": "INVOKES", "source_id": eid, "target_id": callee}
                )
        retry = ev.get("retries_event_id")
        if retry:
            lineage.retries[eid] = retry
            lineage.expected_relationships.append(
                {"rel_type": "RETRIES", "source_id": eid, "target_id": retry}
            )
    lineage.artifact_producers = producers
    lineage.artifact_consumers = consumers
    return lineage
