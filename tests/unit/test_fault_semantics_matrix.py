"""Phase 2.5.1: per-fault-type observable / GT / leakage / validator coverage."""

from __future__ import annotations

import pytest

from agenttrust import ProvenanceTrace
from agenttrust.benchmark import (
    BenchmarkConfig,
    BenchmarkGenerator,
    FaultType,
    ScenarioId,
    ScaleTier,
    TopologyId,
    validate_generated_trace,
)
from agenttrust.benchmark.faults import (
    PROHIBITED_ANSWER_KEYS,
    SENTINEL_CORRUPTION_HASH,
    SENTINEL_INCORRECT_OUTPUT_HASH,
)
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.schema.enums import RelationshipType


def _gen(fault: FaultType, *, topology=TopologyId.SEQUENTIAL, seed: int = 1, incomplete: bool = False):
    return BenchmarkGenerator().generate(
        BenchmarkConfig(
            ScenarioId.FINANCIAL_LOAN,
            topology,
            ScaleTier.S1,
            seed=seed,
            fault_types=(fault.value,),
            incomplete=incomplete or fault == FaultType.INCOMPLETE_TRACE,
        )
    )


def _assert_no_leakage(pkg) -> None:
    for e in pkg.events:
        meta = e.get("metadata") or {}
        if isinstance(meta, dict):
            assert not any(str(k).startswith("gt_") for k in meta)
            assert PROHIBITED_ANSWER_KEYS.isdisjoint(meta.keys())
    for a in pkg.artifacts:
        meta = a.get("metadata") or {}
        if isinstance(meta, dict):
            assert not any(str(k).startswith("gt_") for k in meta)
            assert PROHIBITED_ANSWER_KEYS.isdisjoint(meta.keys())


@pytest.mark.parametrize("fault", list(FaultType))
def test_each_fault_has_gt_and_passes_strict_validation(fault: FaultType):
    topo = TopologyId.MIXED if fault == FaultType.DELEGATION_FAILURE else TopologyId.SEQUENTIAL
    pkg = _gen(fault, topology=topo, seed=400 + list(FaultType).index(fault))
    assert pkg.ground_truth.interventions
    assert any(i.fault_type == fault.value for i in pkg.ground_truth.interventions)
    _assert_no_leakage(pkg)
    v = validate_generated_trace(pkg, require_complete=False, check_fault_observables=True)
    assert v.ok, (fault, v.errors)


def test_missing_dependency_observable():
    pkg = _gen(FaultType.MISSING_DEPENDENCY, seed=10)
    iv = pkg.ground_truth.interventions[0]
    phantom = iv.parameters["phantom_dependency"]
    ev = next(e for e in pkg.events if e["event_id"] == iv.injection_location)
    assert phantom in ev["dependency_event_ids"]
    assert phantom in pkg.ground_truth.quality.missing_dependency_refs


def test_incorrect_tool_output_success_with_hash_mismatch():
    pkg = _gen(FaultType.INCORRECT_TOOL_OUTPUT, seed=11)
    iv = pkg.ground_truth.interventions[0]
    ev = next(e for e in pkg.events if e["event_id"] == iv.injection_location)
    art = next(a for a in pkg.artifacts if a["artifact_id"] == iv.parameters["artifact_id"])
    assert ev["status"] == "success"
    assert art["content_hash"] == SENTINEL_INCORRECT_OUTPUT_HASH
    assert art["content_hash"] != iv.parameters["expected_content_hash"]


def test_tool_call_failure_status():
    pkg = _gen(FaultType.TOOL_CALL_FAILURE, seed=12)
    iv = pkg.ground_truth.interventions[0]
    ev = next(e for e in pkg.events if e["event_id"] == iv.injection_location)
    assert ev["status"] == "failure"


def test_artifact_corruption_expected_observed_mismatch():
    pkg = _gen(FaultType.ARTIFACT_CORRUPTION, seed=13)
    iv = pkg.ground_truth.interventions[0]
    art = next(a for a in pkg.artifacts if a["artifact_id"] == iv.parameters["artifact_id"])
    assert art["content_hash"] == SENTINEL_CORRUPTION_HASH
    assert iv.parameters["expected_content_hash"] != iv.parameters["observed_content_hash"]
    assert (art.get("metadata") or {}).get("corrupted") != "true"


def test_retry_storm_chain_and_distinct_artifacts():
    pkg = _gen(FaultType.RETRY_STORM, seed=14)
    iv = pkg.ground_truth.interventions[0]
    retries = iv.parameters["retry_event_ids"]
    assert len(retries) == 3
    outs = []
    for rid in retries:
        ev = next(e for e in pkg.events if e["event_id"] == rid)
        assert ev.get("retries_event_id")
        outs.extend(ev.get("output_artifact_ids") or [])
    assert len(set(outs)) == 3
    pt = ProvenanceTrace()
    pt.load_records(*pkg.algorithm_inputs())
    for rid in retries:
        prior = next(e for e in pkg.events if e["event_id"] == rid)["retries_event_id"]
        assert RelationshipType.RETRIES.value in (pt.graph.get_edge_data(rid, prior) or {})


def test_delegation_callee_failed_and_missing_callee():
    mixed = _gen(FaultType.DELEGATION_FAILURE, topology=TopologyId.MIXED, seed=15)
    iv_m = mixed.ground_truth.interventions[0]
    assert iv_m.parameters["mode"] in {"callee_failed", "missing_callee"}
    if iv_m.parameters["mode"] == "callee_failed":
        callee = next(e for e in mixed.events if e["event_id"] == iv_m.parameters["callee_event_id"])
        assert callee["status"] == "failure"
        caller = next(e for e in mixed.events if e["event_id"] == iv_m.parameters["caller_event_id"])
        assert iv_m.parameters["callee_event_id"] in (caller.get("invokes_event_ids") or [])

    seq = _gen(FaultType.DELEGATION_FAILURE, topology=TopologyId.SEQUENTIAL, seed=16)
    iv_s = seq.ground_truth.interventions[0]
    assert iv_s.parameters["mode"] == "missing_callee"
    phantom = iv_s.parameters["phantom_callee"]
    caller = next(e for e in seq.events if e["event_id"] == iv_s.injection_location)
    assert phantom in (caller.get("invokes_event_ids") or [])
    assert phantom not in {e["event_id"] for e in seq.events}


def test_misleading_observation_not_in_p1_p2():
    pkg = _gen(FaultType.MISLEADING_OBSERVATION, seed=17)
    iv = pkg.ground_truth.interventions[0]
    early = iv.parameters["observed_after"]
    observer = iv.parameters["observer_event_id"]
    obs_ev = next(e for e in pkg.events if e["event_id"] == observer)
    assert early in (obs_ev.get("observed_after_event_ids") or [])
    assert early not in (obs_ev.get("dependency_event_ids") or [])
    pt = ProvenanceTrace()
    pt.load_records(*pkg.algorithm_inputs())
    assert RelationshipType.OBSERVED_AFTER.value in (pt.graph.get_edge_data(early, observer) or {})
    for kind in (ProjectionKind.P1_DIRECT, ProjectionKind.P2_ARTIFACT_BRIDGE):
        proj = pt.project(kind)
        assert not proj.graph.has_edge(early, observer)


def test_incomplete_trace_removed_and_recorded():
    pkg = _gen(FaultType.INCOMPLETE_TRACE, incomplete=True, seed=18)
    removed = pkg.ground_truth.interventions[0].parameters["removed_event_id"]
    assert removed not in {e["event_id"] for e in pkg.events}
    assert removed in pkg.ground_truth.quality.missing_event_ids


def test_conflicting_outputs_inconsistent_decisions():
    pkg = _gen(FaultType.CONFLICTING_OUTPUTS, seed=19)
    iv = pkg.ground_truth.interventions[0]
    arts = [a for a in pkg.artifacts if a["artifact_id"] in set(iv.affected_artifact_ids)]
    decisions = [a["metadata"]["decision"] for a in arts]
    assert len(set(decisions)) >= 2
    assert len({a["content_hash"] for a in arts}) >= 2
    _assert_no_leakage(pkg)
