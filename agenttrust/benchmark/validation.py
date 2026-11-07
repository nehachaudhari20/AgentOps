"""
Validate generated traces: schema load, GT consistency, and intentional-defect awareness.

Deliberately injected defects are allowed only when declared by interventions.
Does not silently repair inconsistencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agenttrust.benchmark.faults import (
    FaultType,
    SENTINEL_CORRUPTION_HASH,
    SENTINEL_INCORRECT_OUTPUT_HASH,
    intentional_missing_dependency_refs,
    intentional_missing_event_ids,
)
from agenttrust.benchmark.generator import GeneratedTrace
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth
from agenttrust.benchmark.manifest import BenchmarkConfig, ScenarioId, TopologyId, TraceManifest, ScaleTier
from agenttrust.mlpg.projections import ProjectionKind, project_attribution_dag
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import RelationshipType


PROHIBITED_META_PREFIXES = ("gt_",)


@dataclass
class BenchmarkValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    incomplete: bool = False
    suitable_for_dag_attribution: Optional[bool] = None
    n_events: int = 0
    n_artifacts: int = 0
    ground_truth_failures: int = 0
    intentional_defects_acknowledged: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "incomplete": self.incomplete,
            "suitable_for_dag_attribution": self.suitable_for_dag_attribution,
            "n_events": self.n_events,
            "n_artifacts": self.n_artifacts,
            "ground_truth_failures": self.ground_truth_failures,
            "intentional_defects_acknowledged": list(self.intentional_defects_acknowledged),
        }


def validate_generated_trace(
    trace: GeneratedTrace,
    *,
    require_complete: bool = False,
    load_provenance: bool = True,
    verify_fingerprint: bool = True,
    check_fault_observables: bool = True,
) -> BenchmarkValidationResult:
    """Full package validation for an in-memory GeneratedTrace."""
    return validate_package(
        events=trace.events,
        artifacts=trace.artifacts,
        manifest=trace.manifest,
        ground_truth=trace.ground_truth,
        config=trace.config,
        require_complete=require_complete,
        load_provenance=load_provenance,
        verify_fingerprint=verify_fingerprint,
        check_fault_observables=check_fault_observables,
    )


def validate_package(
    *,
    events: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    manifest: TraceManifest,
    ground_truth: BenchmarkGroundTruth,
    config: Optional[BenchmarkConfig] = None,
    require_complete: bool = False,
    load_provenance: bool = True,
    verify_fingerprint: bool = True,
    check_fault_observables: bool = True,
    expected_trace_dirname: Optional[str] = None,
) -> BenchmarkValidationResult:
    """
    Comprehensive consistency validation.

    Distinguishes intentional intervention defects from accidental generator defects.
    """
    result = BenchmarkValidationResult(ok=True)
    result.n_events = len(events)
    result.n_artifacts = len(artifacts)

    eids = [e["event_id"] for e in events]
    aids = [a["artifact_id"] for a in artifacts]
    eid_set = set(eids)
    aid_set = set(aids)
    events_by_id = {e["event_id"]: e for e in events}
    arts_by_id = {a["artifact_id"]: a for a in artifacts}

    if len(eids) != len(eid_set):
        result.errors.append("Duplicate event_id within trace")
    if len(aids) != len(aid_set):
        result.errors.append("Duplicate artifact_id within trace")

    # Manifest counts
    if manifest.actual_event_count != len(events):
        result.errors.append(
            f"Manifest actual_event_count {manifest.actual_event_count} != {len(events)}"
        )
    if manifest.artifact_count != len(artifacts):
        result.errors.append(
            f"Manifest artifact_count {manifest.artifact_count} != {len(artifacts)}"
        )

    # Trace ID agreement
    if ground_truth.trace_id != manifest.trace_id:
        result.errors.append("Ground-truth trace_id mismatch vs manifest")
    if expected_trace_dirname is not None and expected_trace_dirname != manifest.trace_id:
        result.errors.append(
            f"Trace directory name {expected_trace_dirname!r} != manifest.trace_id {manifest.trace_id!r}"
        )

    # Interventions
    interventions = list(ground_truth.interventions)
    iv_ids = [i.intervention_id for i in interventions]
    if len(iv_ids) != len(set(iv_ids)):
        result.errors.append("Duplicate intervention_id in ground truth")
    if manifest.intervention_count != len(interventions):
        result.errors.append(
            f"Manifest intervention_count {manifest.intervention_count} != {len(interventions)}"
        )

    gt_faults = sorted({i.fault_type for i in interventions})
    man_faults = sorted(set(manifest.fault_types))
    if man_faults != gt_faults:
        # Allow incomplete_trace auto-added on either side when incomplete flag set
        if set(man_faults) != set(gt_faults):
            result.errors.append(
                f"Manifest fault_types {man_faults} disagree with intervention records {gt_faults}"
            )

    allowed_missing_events = intentional_missing_event_ids(interventions)
    allowed_missing_refs = intentional_missing_dependency_refs(interventions)
    if allowed_missing_events:
        result.intentional_defects_acknowledged.append(
            f"missing_events={sorted(allowed_missing_events)}"
        )
    if allowed_missing_refs:
        result.intentional_defects_acknowledged.append(
            f"missing_refs={sorted(allowed_missing_refs)}"
        )

    # Lineage references
    lineage = ground_truth.lineage
    for eid, deps in lineage.event_dependencies.items():
        if eid not in eid_set and eid not in allowed_missing_events:
            result.errors.append(f"Lineage subject event unknown: {eid}")
        for dep in deps:
            if dep not in eid_set and dep not in allowed_missing_refs and dep not in allowed_missing_events:
                result.errors.append(
                    f"Lineage dependency {dep!r} of {eid!r} unknown and not an intentional missing ref"
                )

    for aid, producer in lineage.artifact_producers.items():
        if aid not in aid_set:
            result.errors.append(f"Lineage producer artifact unknown: {aid}")
        if producer not in eid_set and producer not in allowed_missing_events:
            result.errors.append(f"Lineage producer event unknown: {producer}")

    for aid, consumers in lineage.artifact_consumers.items():
        if aid not in aid_set:
            result.errors.append(f"Lineage consumer artifact unknown: {aid}")
        for cid in consumers:
            if cid not in eid_set and cid not in allowed_missing_events:
                result.errors.append(f"Lineage consumer event unknown: {cid}")

    for caller, callees in lineage.invocations.items():
        if caller not in eid_set and caller not in allowed_missing_events:
            result.errors.append(f"Lineage invocation caller unknown: {caller}")
        for callee in callees:
            if (
                callee not in eid_set
                and callee not in allowed_missing_refs
                and callee not in allowed_missing_events
            ):
                result.errors.append(
                    f"Lineage invocation callee {callee!r} unknown and not intentional"
                )

    for retry_e, prior in lineage.retries.items():
        if retry_e not in eid_set:
            result.errors.append(f"Lineage retry event unknown: {retry_e}")
        if prior not in eid_set and prior not in allowed_missing_events:
            result.errors.append(f"Lineage retry parent unknown: {prior}")

    # Intervention affected IDs accounted for
    for iv in interventions:
        for eid in iv.affected_event_ids:
            if (
                eid not in eid_set
                and eid not in allowed_missing_events
                and eid not in allowed_missing_refs
            ):
                result.errors.append(
                    f"Intervention {iv.intervention_id} affected unknown event {eid}"
                )
        for aid in iv.affected_artifact_ids:
            if aid not in aid_set:
                result.errors.append(
                    f"Intervention {iv.intervention_id} affected unknown artifact {aid}"
                )

    # Outcomes
    outcomes = list(manifest.outcome_event_ids)
    structural_outcomes = list(ground_truth.structural.outcome_event_ids)
    if set(outcomes) != set(structural_outcomes):
        result.errors.append("Manifest outcome_event_ids disagree with structural GT")
    if not outcomes:
        if not (
            manifest.incomplete
            or any(i.fault_type == FaultType.INCOMPLETE_TRACE.value for i in interventions)
        ):
            result.warnings.append("No outcome_event_ids recorded in manifest")
    else:
        missing_out = [o for o in outcomes if o not in eid_set]
        if missing_out and not manifest.incomplete:
            result.errors.append(f"Outcome ids missing from events: {missing_out}")

    # Structural IDs vs generated records
    agents_in_events = sorted({e.get("agent_id") for e in events if e.get("agent_id")})
    models_in_events = sorted({e.get("model_id") for e in events if e.get("model_id")})
    tools_in_events = sorted({e.get("tool_id") for e in events if e.get("tool_id")})
    if sorted(a for a in ground_truth.structural.agent_ids) != sorted(
        set(ground_truth.structural.agent_ids)
    ):
        result.warnings.append("Structural agent_ids contain duplicates")
    # Agents listed in GT should cover agents that appear (roster may be larger than used)
    for a in agents_in_events:
        if a not in set(ground_truth.structural.agent_ids):
            result.errors.append(f"Event agent_id {a!r} absent from structural GT")
    if sorted(models_in_events) != sorted(ground_truth.structural.model_ids):
        result.errors.append(
            f"Structural model_ids {ground_truth.structural.model_ids} != observed {models_in_events}"
        )
    if sorted(tools_in_events) != sorted(ground_truth.structural.tool_ids):
        result.errors.append(
            f"Structural tool_ids {ground_truth.structural.tool_ids} != observed {tools_in_events}"
        )

    for eid, cat in ground_truth.structural.event_categories.items():
        if eid in allowed_missing_events:
            continue
        if eid not in events_by_id:
            result.errors.append(f"Structural category for unknown event {eid}")
        elif events_by_id[eid].get("category") != cat:
            result.errors.append(f"Structural category mismatch for {eid}")

    # No gt_* labels in algorithm-facing metadata
    for e in events:
        meta = e.get("metadata") or {}
        if isinstance(meta, dict):
            for k in meta:
                if any(str(k).startswith(p) for p in PROHIBITED_META_PREFIXES):
                    result.errors.append(f"Event {e.get('event_id')} contains prohibited metadata key {k}")
    for a in artifacts:
        meta = a.get("metadata") or {}
        if isinstance(meta, dict):
            for k in meta:
                if any(str(k).startswith(p) for p in PROHIBITED_META_PREFIXES):
                    result.errors.append(
                        f"Artifact {a.get('artifact_id')} contains prohibited metadata key {k}"
                    )

    # Fingerprint — prefer exact config match; allow historical case where
    # manifest.incomplete reflects post-fault quality while the fingerprint
    # was computed from the generation-request flag (often False for planted
    # missing_dependency alone).
    if verify_fingerprint and config is not None:
        if config.fingerprint() != manifest.config_fingerprint:
            from dataclasses import replace

            alt = replace(config, incomplete=not config.incomplete)
            if alt.fingerprint() == manifest.config_fingerprint:
                result.warnings.append(
                    "config_fingerprint matches generation-request incomplete flag "
                    "(differs from post-fault manifest.incomplete quality bit)"
                )
            else:
                # Last resort: rebuild from manifest identity fields with incomplete=False
                try:
                    req = BenchmarkConfig(
                        scenario_id=ScenarioId(manifest.scenario_id),
                        topology_id=TopologyId(manifest.topology_id),
                        scale_tier=ScaleTier(manifest.scale_tier),
                        seed=manifest.seed,
                        fault_types=tuple(
                            f
                            for f in manifest.fault_types
                            if f != FaultType.INCOMPLETE_TRACE.value or config.incomplete
                        ),
                        incomplete=False,
                        generator_version=manifest.generator_version,
                    )
                    if req.fingerprint() == manifest.config_fingerprint:
                        result.warnings.append(
                            "config_fingerprint verified against request-incomplete=False reconstruction"
                        )
                    else:
                        result.errors.append(
                            "Manifest config_fingerprint does not recompute from config"
                        )
                except Exception:
                    result.errors.append(
                        "Manifest config_fingerprint does not recompute from config"
                    )

    # Quality GT vs intentional missing
    for mid in ground_truth.quality.missing_dependency_refs:
        if mid not in allowed_missing_refs and mid not in allowed_missing_events:
            # May also be dangling after incomplete removal
            if mid in eid_set:
                result.errors.append(f"Quality missing_dependency_ref {mid} still present as event")
    for mid in ground_truth.quality.missing_event_ids:
        if mid in eid_set:
            result.errors.append(f"Quality missing_event_id {mid} still present in events")

    if check_fault_observables:
        _check_fault_observables(
            result,
            events_by_id=events_by_id,
            arts_by_id=arts_by_id,
            interventions=interventions,
        )

    if load_provenance:
        pt = ProvenanceTrace()
        report = pt.load_records(events, artifacts)
        completeness = pt.completeness()
        result.incomplete = completeness.incomplete
        result.suitable_for_dag_attribution = completeness.suitable_for_dag_attribution

        if require_complete and completeness.incomplete:
            result.errors.append("Trace incomplete but require_complete=True")

        if manifest.incomplete and not completeness.incomplete:
            result.warnings.append(
                "Manifest marked incomplete but ProvenanceTrace completeness.incomplete is False"
            )
        if (not manifest.incomplete) and completeness.incomplete:
            result.errors.append(
                "Complete trace loaded as incomplete "
                f"(missing parents: {list(completeness.missing_dependency_parents)[:5]})"
            )

        if completeness.has_dependency_cycle and not manifest.incomplete:
            result.errors.append("Unexpected dependency cycle in generated DAG scenario")

        if report is None:
            result.errors.append("Validation report missing")

        # OBSERVED_AFTER must not enter P1/P2
        for kind in (ProjectionKind.P1_DIRECT, ProjectionKind.P2_ARTIFACT_BRIDGE):
            proj = project_attribution_dag(pt.graph, kind)
            for e in proj.edges:
                if e.origin == RelationshipType.OBSERVED_AFTER.value:
                    result.errors.append(f"{kind.value} contains OBSERVED_AFTER origin")
            # Also ensure no projected edge came solely from observed_after field
            for u, v, data in proj.graph.edges(data=True):
                if data.get("origin") == "OBSERVED_AFTER":
                    result.errors.append(f"{kind.value} graph edge marked OBSERVED_AFTER")

        # Retry edges present in MLPG when lineage says so
        for retry_e, prior in lineage.retries.items():
            if retry_e in eid_set and prior in eid_set:
                data = pt.graph.get_edge_data(retry_e, prior) or {}
                if RelationshipType.RETRIES.value not in data:
                    result.errors.append(f"Missing MLPG RETRIES edge {retry_e}→{prior}")

        # Invoke edges when both endpoints exist
        for caller, callees in lineage.invocations.items():
            for callee in callees:
                if caller in eid_set and callee in eid_set:
                    data = pt.graph.get_edge_data(caller, callee) or {}
                    if RelationshipType.INVOKES.value not in data:
                        result.errors.append(f"Missing MLPG INVOKES edge {caller}→{callee}")

    result.ground_truth_failures = len(result.errors)
    result.ok = len(result.errors) == 0
    return result


def _check_fault_observables(
    result: BenchmarkValidationResult,
    *,
    events_by_id: dict[str, dict[str, Any]],
    arts_by_id: dict[str, dict[str, Any]],
    interventions: list,
) -> None:
    """Verify each intervention's claimed observable effect is present (or intentionally absent)."""
    for iv in interventions:
        ft = iv.fault_type
        params = iv.parameters or {}

        if ft == FaultType.MISSING_DEPENDENCY.value:
            loc = iv.injection_location
            phantom = params.get("phantom_dependency")
            ev = events_by_id.get(loc)
            if ev is None:
                result.errors.append(
                    f"Intervention {iv.intervention_id} missing_dependency location absent"
                )
            elif phantom not in (ev.get("dependency_event_ids") or []):
                result.errors.append(
                    f"Intervention {iv.intervention_id} phantom dependency not observable on event"
                )

        elif ft == FaultType.INCORRECT_TOOL_OUTPUT.value:
            aid = params.get("artifact_id") or (iv.affected_artifact_ids[0] if iv.affected_artifact_ids else None)
            art = arts_by_id.get(aid) if aid else None
            ev = events_by_id.get(iv.injection_location)
            if art is None:
                result.errors.append(
                    f"Intervention {iv.intervention_id} incorrect_tool_output artifact missing"
                )
            else:
                if art.get("content_hash") != params.get("observed_content_hash", SENTINEL_INCORRECT_OUTPUT_HASH):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} observed hash mismatch"
                    )
                if params.get("expected_content_hash") == art.get("content_hash"):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} expected hash equals observed (no corruption)"
                    )
            if ev is not None and ev.get("status") != "success":
                result.errors.append(
                    f"Intervention {iv.intervention_id} incorrect_tool_output must keep status=success"
                )

        elif ft == FaultType.TOOL_CALL_FAILURE.value:
            ev = events_by_id.get(iv.injection_location)
            if ev is None or ev.get("status") != "failure":
                result.errors.append(
                    f"Intervention {iv.intervention_id} tool_call_failure status not failure"
                )

        elif ft == FaultType.ARTIFACT_CORRUPTION.value:
            aid = params.get("artifact_id") or (
                iv.affected_artifact_ids[0] if iv.affected_artifact_ids else None
            )
            art = arts_by_id.get(aid) if aid else None
            if art is None:
                result.errors.append(
                    f"Intervention {iv.intervention_id} corruption artifact missing"
                )
            else:
                if art.get("content_hash") != params.get("observed_content_hash", SENTINEL_CORRUPTION_HASH):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} corruption observed hash mismatch"
                    )
                if not params.get("expected_content_hash"):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} missing expected_content_hash in GT"
                    )
                elif params.get("expected_content_hash") == art.get("content_hash"):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} corruption expected==observed"
                    )
                meta = art.get("metadata") or {}
                if isinstance(meta, dict) and meta.get("corrupted") == "true":
                    result.errors.append(
                        f"Intervention {iv.intervention_id} leaked corrupted label into algorithm input"
                    )

        elif ft == FaultType.RETRY_STORM.value:
            for rid in params.get("retry_event_ids") or []:
                if rid not in events_by_id:
                    result.errors.append(
                        f"Intervention {iv.intervention_id} retry event {rid} missing"
                    )
                else:
                    parent = events_by_id[rid].get("retries_event_id")
                    if not parent:
                        result.errors.append(
                            f"Intervention {iv.intervention_id} retry {rid} lacks retries_event_id"
                        )

        elif ft == FaultType.DELEGATION_FAILURE.value:
            mode = params.get("mode")
            if mode == "missing_callee":
                loc = iv.injection_location
                ev = events_by_id.get(loc)
                phantom = params.get("phantom_callee")
                if ev is None or phantom not in (ev.get("invokes_event_ids") or []):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} missing_callee not observable"
                    )
            elif mode == "callee_failed":
                callee = events_by_id.get(params.get("callee_event_id"))
                if callee is None or callee.get("status") != "failure":
                    result.errors.append(
                        f"Intervention {iv.intervention_id} callee_failed not observable"
                    )

        elif ft == FaultType.CONFLICTING_OUTPUTS.value:
            labels = set()
            for aid in iv.affected_artifact_ids:
                art = arts_by_id.get(aid)
                if art and isinstance(art.get("metadata"), dict):
                    labels.add(art["metadata"].get("conflict_label"))
            if labels != {"approve", "reject"}:
                result.errors.append(
                    f"Intervention {iv.intervention_id} conflicting labels not observable: {labels}"
                )

        elif ft == FaultType.INCOMPLETE_TRACE.value:
            removed = params.get("removed_event_id")
            if removed and removed in events_by_id:
                result.errors.append(
                    f"Intervention {iv.intervention_id} removed event still present"
                )

        elif ft == FaultType.MISLEADING_OBSERVATION.value:
            observer = events_by_id.get(params.get("observer_event_id") or iv.injection_location)
            early = params.get("observed_after")
            if observer is None:
                result.errors.append(
                    f"Intervention {iv.intervention_id} observer event missing"
                )
            else:
                if early not in (observer.get("observed_after_event_ids") or []):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} OBSERVED_AFTER not set"
                    )
                if early in (observer.get("dependency_event_ids") or []):
                    result.errors.append(
                        f"Intervention {iv.intervention_id} OBSERVED_AFTER incorrectly also DEPENDS_ON"
                    )


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


def load_and_validate_trace_dir(
    trace_dir: Path,
    *,
    pilot_root: Optional[Path] = None,
    require_complete: bool = False,
    load_provenance: bool = True,
) -> BenchmarkValidationResult:
    """Validate an on-disk trace package with separate GT/manifest files."""
    import json

    trace_dir = Path(trace_dir)
    pilot_root = Path(pilot_root) if pilot_root else trace_dir.parent.parent
    tid = trace_dir.name
    events = json.loads((trace_dir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((trace_dir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    man = TraceManifest.from_dict(
        json.loads((pilot_root / "manifests" / f"{tid}.json").read_text(encoding="utf-8"))
    )
    gt = BenchmarkGroundTruth.from_dict(
        json.loads((pilot_root / "ground_truth" / f"{tid}.json").read_text(encoding="utf-8"))
    )
    config = None
    try:
        config = BenchmarkConfig(
            scenario_id=ScenarioId(man.scenario_id),
            topology_id=TopologyId(man.topology_id),
            scale_tier=ScaleTier(man.scale_tier),
            seed=man.seed,
            fault_types=tuple(man.fault_types),
            incomplete=man.incomplete,
            generator_version=man.generator_version,
        )
    except Exception:
        config = None
    return validate_package(
        events=events,
        artifacts=arts,
        manifest=man,
        ground_truth=gt,
        config=config,
        require_complete=require_complete,
        load_provenance=load_provenance,
        verify_fingerprint=config is not None,
        expected_trace_dirname=tid,
    )
