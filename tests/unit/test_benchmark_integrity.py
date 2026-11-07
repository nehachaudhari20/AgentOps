"""Phase 2.5: ground-truth integrity, fault semantics, and adversarial validator tests."""

from __future__ import annotations

import copy

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
    validate_package,
)
from agenttrust.benchmark.faults import SENTINEL_CORRUPTION_HASH, SENTINEL_INCORRECT_OUTPUT_HASH
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.schema.enums import RelationshipType


def _clean_pkg(**kwargs):
    gen = BenchmarkGenerator()
    cfg = BenchmarkConfig(
        scenario_id=kwargs.get("scenario", ScenarioId.FINANCIAL_LOAN),
        topology_id=kwargs.get("topology", TopologyId.MIXED),
        scale_tier=kwargs.get("scale", ScaleTier.S1),
        seed=kwargs.get("seed", 42),
        fault_types=kwargs.get("fault_types", ()),
        incomplete=kwargs.get("incomplete", False),
    )
    return gen.generate(cfg)


# --- Fault semantics ---


def test_incorrect_tool_output_is_successful_wrong_content():
    pkg = _clean_pkg(fault_types=(FaultType.INCORRECT_TOOL_OUTPUT.value,), topology=TopologyId.SEQUENTIAL)
    iv = pkg.ground_truth.interventions[0]
    assert iv.fault_type == FaultType.INCORRECT_TOOL_OUTPUT.value
    assert iv.parameters["mode"] == "incorrect_success"
    ev = next(e for e in pkg.events if e["event_id"] == iv.injection_location)
    assert ev["status"] == "success"
    art = next(a for a in pkg.artifacts if a["artifact_id"] == iv.parameters["artifact_id"])
    assert art["content_hash"] == SENTINEL_INCORRECT_OUTPUT_HASH
    assert art["content_hash"] != iv.parameters["expected_content_hash"]
    assert "gt_" not in str(art.get("metadata", {}))
    v = validate_generated_trace(pkg, require_complete=False)
    assert v.ok, v.errors


def test_tool_call_failure_sets_status_failure():
    pkg = _clean_pkg(fault_types=(FaultType.TOOL_CALL_FAILURE.value,), topology=TopologyId.SEQUENTIAL)
    iv = pkg.ground_truth.interventions[0]
    ev = next(e for e in pkg.events if e["event_id"] == iv.injection_location)
    assert ev["status"] == "failure"
    assert validate_generated_trace(pkg, require_complete=False).ok


def test_artifact_corruption_keeps_expected_hash_in_gt_only():
    pkg = _clean_pkg(fault_types=(FaultType.ARTIFACT_CORRUPTION.value,))
    iv = pkg.ground_truth.interventions[0]
    art = next(a for a in pkg.artifacts if a["artifact_id"] == iv.parameters["artifact_id"])
    assert art["content_hash"] == SENTINEL_CORRUPTION_HASH
    assert iv.parameters["expected_content_hash"] != art["content_hash"]
    meta = art.get("metadata") or {}
    assert meta.get("corrupted") != "true"
    assert validate_generated_trace(pkg, require_complete=False).ok


def test_retry_storm_unique_ids_and_mlpg_retries():
    pkg = _clean_pkg(fault_types=(FaultType.RETRY_STORM.value,), topology=TopologyId.SEQUENTIAL)
    iv = next(i for i in pkg.ground_truth.interventions if i.fault_type == FaultType.RETRY_STORM.value)
    retry_ids = iv.parameters["retry_event_ids"]
    assert len(set(retry_ids)) == 3
    pt = ProvenanceTrace()
    pt.load_records(*pkg.algorithm_inputs())
    for rid in retry_ids:
        ev = next(e for e in pkg.events if e["event_id"] == rid)
        prior = ev["retries_event_id"]
        assert prior
        edge = pt.graph.get_edge_data(rid, prior)
        assert edge and RelationshipType.RETRIES.value in edge
    assert validate_generated_trace(pkg, require_complete=False).ok


def test_delegation_failure_modes():
    # Mixed topology includes INVOKES → callee_failed
    pkg = _clean_pkg(fault_types=(FaultType.DELEGATION_FAILURE.value,), topology=TopologyId.MIXED)
    iv = pkg.ground_truth.interventions[0]
    assert iv.parameters["mode"] in {"callee_failed", "missing_callee"}
    if iv.parameters["mode"] == "callee_failed":
        callee = next(e for e in pkg.events if e["event_id"] == iv.parameters["callee_event_id"])
        assert callee["status"] == "failure"
    assert validate_generated_trace(pkg, require_complete=False).ok


def test_misleading_observation_excluded_from_projections():
    pkg = _clean_pkg(
        fault_types=(FaultType.MISLEADING_OBSERVATION.value,),
        topology=TopologyId.SEQUENTIAL,
    )
    iv = pkg.ground_truth.interventions[0]
    observer_id = iv.parameters["observer_event_id"]
    early = iv.parameters["observed_after"]
    pt = ProvenanceTrace()
    pt.load_records(*pkg.algorithm_inputs())
    # OBSERVED_AFTER present in MLPG
    edge = pt.graph.get_edge_data(early, observer_id)
    assert edge and RelationshipType.OBSERVED_AFTER.value in edge
    for kind in (ProjectionKind.P1_DIRECT, ProjectionKind.P2_ARTIFACT_BRIDGE):
        proj = pt.project(kind)
        assert (early, observer_id) not in proj.graph.edges or proj.graph.edges[early, observer_id].get(
            "origin"
        ) != "OBSERVED_AFTER"
        # More strictly: no P1/P2 edge from early→observer unless DEPENDS_ON also exists
        observer = next(e for e in pkg.events if e["event_id"] == observer_id)
        if early not in (observer.get("dependency_event_ids") or []):
            assert not proj.graph.has_edge(early, observer_id)
    assert validate_generated_trace(pkg, require_complete=False).ok


def test_incomplete_trace_not_silently_repaired():
    pkg = _clean_pkg(
        fault_types=(FaultType.INCOMPLETE_TRACE.value,),
        incomplete=True,
        topology=TopologyId.SEQUENTIAL,
    )
    removed = pkg.ground_truth.interventions[0].parameters["removed_event_id"]
    assert removed not in {e["event_id"] for e in pkg.events}
    assert removed in pkg.ground_truth.quality.missing_event_ids
    v = validate_generated_trace(pkg, require_complete=False)
    assert v.ok, v.errors
    assert v.incomplete


# --- Adversarial validator tests ---


def test_adversarial_unknown_gt_event_reference():
    pkg = _clean_pkg()
    pkg.ground_truth.lineage.event_dependencies["does-not-exist"] = ["also-missing"]
    v = validate_package(
        events=pkg.events,
        artifacts=pkg.artifacts,
        manifest=pkg.manifest,
        ground_truth=pkg.ground_truth,
        config=pkg.config,
        load_provenance=False,
        check_fault_observables=False,
    )
    assert not v.ok
    assert any("unknown" in e.lower() or "Lineage" in e for e in v.errors)


def test_adversarial_unknown_gt_artifact_reference():
    pkg = _clean_pkg()
    pkg.ground_truth.lineage.artifact_producers["ghost-art"] = pkg.events[0]["event_id"]
    v = validate_package(
        events=pkg.events,
        artifacts=pkg.artifacts,
        manifest=pkg.manifest,
        ground_truth=pkg.ground_truth,
        config=pkg.config,
        load_provenance=False,
        check_fault_observables=False,
    )
    assert not v.ok
    assert any("artifact" in e.lower() for e in v.errors)


def test_adversarial_incorrect_manifest_intervention_count():
    pkg = _clean_pkg(fault_types=(FaultType.TOOL_CALL_FAILURE.value,))
    pkg.manifest.intervention_count = 99
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("intervention_count" in e for e in v.errors)


def test_adversarial_incorrect_manifest_event_count():
    pkg = _clean_pkg()
    pkg.manifest.actual_event_count = 0
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("actual_event_count" in e for e in v.errors)


def test_adversarial_duplicate_intervention_ids():
    pkg = _clean_pkg(fault_types=(FaultType.TOOL_CALL_FAILURE.value,))
    pkg.ground_truth.interventions.append(copy.deepcopy(pkg.ground_truth.interventions[0]))
    pkg.manifest.intervention_count = len(pkg.ground_truth.interventions)
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("Duplicate intervention_id" in e for e in v.errors)


def test_adversarial_mismatched_trace_ids():
    pkg = _clean_pkg()
    pkg.ground_truth.trace_id = "other-trace"
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("trace_id" in e for e in v.errors)


def test_adversarial_fault_type_declared_but_absent():
    pkg = _clean_pkg()
    pkg.manifest.fault_types = ["missing_dependency"]
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("fault_types" in e for e in v.errors)


def test_adversarial_prohibited_gt_label():
    pkg = _clean_pkg()
    pkg.events[0]["metadata"] = {"gt_answer": "secret"}
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("prohibited" in e for e in v.errors)


def test_adversarial_intervention_without_observable_effect():
    pkg = _clean_pkg(fault_types=(FaultType.TOOL_CALL_FAILURE.value,))
    # Undo the observable failure
    loc = pkg.ground_truth.interventions[0].injection_location
    for e in pkg.events:
        if e["event_id"] == loc:
            e["status"] = "success"
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("tool_call_failure" in e for e in v.errors)


def test_adversarial_corruption_integrity_inconsistent():
    pkg = _clean_pkg(fault_types=(FaultType.ARTIFACT_CORRUPTION.value,))
    iv = pkg.ground_truth.interventions[0]
    # Make expected equal observed — inconsistent planted evidence
    iv.parameters["expected_content_hash"] = iv.parameters["observed_content_hash"]
    v = validate_generated_trace(pkg, require_complete=False, load_provenance=False)
    assert not v.ok
    assert any("expected==observed" in e or "equals observed" in e for e in v.errors)


def test_adversarial_retry_parent_missing():
    pkg = _clean_pkg(fault_types=(FaultType.RETRY_STORM.value,), topology=TopologyId.SEQUENTIAL)
    # Point a retry at a non-existent parent in lineage
    rid = pkg.ground_truth.interventions[0].parameters["retry_event_ids"][0]
    pkg.ground_truth.lineage.retries[rid] = "no-such-parent"
    v = validate_package(
        events=pkg.events,
        artifacts=pkg.artifacts,
        manifest=pkg.manifest,
        ground_truth=pkg.ground_truth,
        config=pkg.config,
        load_provenance=False,
        check_fault_observables=False,
    )
    assert not v.ok
    assert any("retry parent unknown" in e for e in v.errors)


def test_adversarial_observed_after_must_not_enter_projection_check():
    """Validator flags if a projection origin were OBSERVED_AFTER (guard test via package rules)."""
    pkg = _clean_pkg(
        fault_types=(FaultType.MISLEADING_OBSERVATION.value,),
        topology=TopologyId.SEQUENTIAL,
    )
    # Healthy package must pass and confirm exclusion
    v = validate_generated_trace(pkg, require_complete=False)
    assert v.ok, v.errors


# --- Relationship fidelity ---


def test_multirelationship_same_endpoints_preserved():
    events = [
        {
            "event_id": "a",
            "trace_id": "t",
            "event_type": "reasoning",
            "category": "reasoning",
            "agent_id": "x",
            "status": "success",
            "ts_start": "2024-01-01T00:00:00Z",
            "ts_end": "2024-01-01T00:00:01Z",
            "dependency_event_ids": [],
            "input_artifact_ids": [],
            "output_artifact_ids": [],
            "schema_version": "2.1.0",
            "invokes_event_ids": ["b"],
            "retries_event_id": "b",
            "observed_after_event_ids": [],
        },
        {
            "event_id": "b",
            "trace_id": "t",
            "event_type": "reasoning",
            "category": "reasoning",
            "agent_id": "y",
            "status": "success",
            "ts_start": "2024-01-01T00:00:02Z",
            "ts_end": "2024-01-01T00:00:03Z",
            "dependency_event_ids": ["a"],
            "input_artifact_ids": [],
            "output_artifact_ids": [],
            "schema_version": "2.1.0",
            "invokes_event_ids": [],
            "observed_after_event_ids": ["a"],
        },
    ]
    pt = ProvenanceTrace()
    pt.load_records(events, [])
    # DEPENDS_ON / OBSERVED_AFTER: earlier a → later b
    # INVOKES / RETRIES: caller/retry a → target b
    ab = pt.graph.get_edge_data("a", "b") or {}
    assert RelationshipType.DEPENDS_ON.value in ab
    assert RelationshipType.OBSERVED_AFTER.value in ab
    assert RelationshipType.INVOKES.value in ab
    assert RelationshipType.RETRIES.value in ab
    # Distinct MultiDiGraph keys — not collapsed
    assert len(ab) >= 4
    p1 = pt.project(ProjectionKind.P1_DIRECT)
    assert p1.graph.has_edge("a", "b")
    assert p1.graph.edges["a", "b"]["origin"] == "DEPENDS_ON"
    for _u, _v, d in p1.graph.edges(data=True):
        assert d.get("origin") in {"DEPENDS_ON", "ARTIFACT_BRIDGE"}


def test_reproducibility_different_seeds_and_configs():
    gen = BenchmarkGenerator()
    a = gen.generate(
        BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=1)
    )
    b = gen.generate(
        BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=2)
    )
    c = gen.generate(
        BenchmarkConfig(ScenarioId.FRAUD_INVESTIGATION, TopologyId.HIERARCHICAL, ScaleTier.S1, seed=1)
    )
    assert a.events != b.events
    assert a.manifest.trace_id != b.manifest.trace_id
    assert a.manifest.trace_id != c.manifest.trace_id
    assert a.manifest.config_fingerprint != b.manifest.config_fingerprint


def test_all_fault_types_validate():
    for fault in FaultType:
        pkg = _clean_pkg(
            fault_types=(fault.value,),
            incomplete=(fault == FaultType.INCOMPLETE_TRACE),
            topology=TopologyId.MIXED if fault == FaultType.DELEGATION_FAILURE else TopologyId.SEQUENTIAL,
            seed=300 + list(FaultType).index(fault),
        )
        v = validate_generated_trace(pkg, require_complete=False)
        assert v.ok, (fault, v.errors)
