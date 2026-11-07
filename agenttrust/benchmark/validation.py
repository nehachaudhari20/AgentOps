"""Validate generated traces against schema, GT consistency, and pipeline load."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agenttrust.benchmark.generator import GeneratedTrace
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth
from agenttrust.benchmark.manifest import TraceManifest
from agenttrust.provenance_trace import ProvenanceTrace


@dataclass
class BenchmarkValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    incomplete: bool = False
    suitable_for_dag_attribution: Optional[bool] = None
    n_events: int = 0
    n_artifacts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "incomplete": self.incomplete,
            "suitable_for_dag_attribution": self.suitable_for_dag_attribution,
            "n_events": self.n_events,
            "n_artifacts": self.n_artifacts,
        }


def validate_generated_trace(
    trace: GeneratedTrace,
    *,
    require_complete: bool = False,
    load_provenance: bool = True,
) -> BenchmarkValidationResult:
    """
    Schema + uniqueness + GT consistency checks.

    Intentionally incomplete traces are allowed unless require_complete=True.
    Does not silently repair records.
    """
    result = BenchmarkValidationResult(ok=True)
    events = trace.events
    artifacts = trace.artifacts
    result.n_events = len(events)
    result.n_artifacts = len(artifacts)

    eids = [e["event_id"] for e in events]
    aids = [a["artifact_id"] for a in artifacts]
    if len(eids) != len(set(eids)):
        result.errors.append("Duplicate event_id within trace")
    if len(aids) != len(set(aids)):
        result.errors.append("Duplicate artifact_id within trace")

    if trace.manifest.actual_event_count != len(events):
        result.errors.append(
            f"Manifest actual_event_count {trace.manifest.actual_event_count} != {len(events)}"
        )
    if trace.manifest.artifact_count != len(artifacts):
        result.errors.append(
            f"Manifest artifact_count {trace.manifest.artifact_count} != {len(artifacts)}"
        )
    if trace.ground_truth.trace_id != trace.manifest.trace_id:
        result.errors.append("Ground-truth trace_id mismatch vs manifest")

    # Outcome presence for complete traces
    outcomes = trace.manifest.outcome_event_ids
    if not outcomes:
        result.warnings.append("No outcome_event_ids recorded in manifest")
    else:
        missing_out = [o for o in outcomes if o not in set(eids)]
        if missing_out and not trace.manifest.incomplete:
            result.errors.append(f"Outcome ids missing from events: {missing_out}")

    # GT intervention ids unique
    iv_ids = [i.intervention_id for i in trace.ground_truth.interventions]
    if len(iv_ids) != len(set(iv_ids)):
        result.errors.append("Duplicate intervention_id in ground truth")

    if load_provenance:
        pt = ProvenanceTrace()
        report = pt.load_records(events, artifacts)
        completeness = pt.completeness()
        result.incomplete = completeness.incomplete
        result.suitable_for_dag_attribution = completeness.suitable_for_dag_attribution

        if require_complete and completeness.incomplete:
            result.errors.append("Trace incomplete but require_complete=True")

        if trace.manifest.incomplete and not completeness.incomplete:
            # Incomplete injection may only remove events that nothing depended on
            result.warnings.append(
                "Manifest marked incomplete but ProvenanceTrace completeness.incomplete is False"
            )
        if (not trace.manifest.incomplete) and completeness.incomplete:
            result.errors.append(
                "Complete pilot trace loaded as incomplete "
                f"(missing parents: {list(completeness.missing_dependency_parents)[:5]})"
            )

        # Cycles: DAG scenarios should not have dependency cycles
        if completeness.has_dependency_cycle and not trace.manifest.incomplete:
            result.errors.append("Unexpected dependency cycle in generated DAG scenario")

        if report is None:
            result.errors.append("Validation report missing")

    result.ok = len(result.errors) == 0
    return result


def assert_deterministic(gen, config) -> None:
    """Raise AssertionError if two generations differ."""
    a = gen.generate(config)
    b = gen.generate(config)
    if a.events != b.events or a.artifacts != b.artifacts:
        raise AssertionError("Non-deterministic event/artifact generation")
    if a.ground_truth.to_dict() != b.ground_truth.to_dict():
        raise AssertionError("Non-deterministic ground truth")
    if a.manifest.to_dict() != b.manifest.to_dict():
        raise AssertionError("Non-deterministic manifest")
