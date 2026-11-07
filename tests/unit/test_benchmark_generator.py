"""Phase 2.4 benchmark generator unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrust.benchmark import (
    SCALE_SPECS,
    BenchmarkConfig,
    BenchmarkGenerator,
    FaultType,
    ScenarioId,
    ScaleTier,
    TopologyId,
    validate_generated_trace,
)
from agenttrust.benchmark.scenarios import assign_agents, get_scenario
from agenttrust.benchmark.topologies import build_topology, list_topologies
from agenttrust.benchmark.validation import assert_deterministic


def test_all_scale_tiers_generate():
    gen = BenchmarkGenerator()
    for tier, spec in SCALE_SPECS.items():
        cfg = BenchmarkConfig(
            ScenarioId.FINANCIAL_LOAN,
            TopologyId.SEQUENTIAL,
            tier,
            seed=11,
        )
        t = gen.generate(cfg)
        assert t.manifest.agent_count == spec["agents"]
        # Allow small construction slack around target
        assert t.manifest.actual_event_count >= max(4, spec["target_events"] - 5)
        assert abs(t.manifest.actual_event_count - spec["target_events"]) <= max(5, spec["target_events"] // 20)


def test_all_topologies_generate_and_validate():
    gen = BenchmarkGenerator()
    for topo in list_topologies():
        cfg = BenchmarkConfig(ScenarioId.RESEARCH_SYNTHESIS, topo, ScaleTier.S1, seed=2)
        t = gen.generate(cfg)
        v = validate_generated_trace(t, require_complete=True)
        assert v.ok, (topo, v.errors)
        eids = [e["event_id"] for e in t.events]
        assert len(eids) == len(set(eids))
        aids = [a["artifact_id"] for a in t.artifacts]
        assert len(aids) == len(set(aids))


def test_deterministic_generation():
    gen = BenchmarkGenerator()
    cfg = BenchmarkConfig(ScenarioId.FRAUD_INVESTIGATION, TopologyId.HIERARCHICAL, ScaleTier.S2, seed=99)
    assert_deterministic(gen, cfg)


def test_event_artifact_uniqueness_and_deps():
    gen = BenchmarkGenerator()
    t = gen.generate(
        BenchmarkConfig(ScenarioId.TRANSACTION_EXECUTION, TopologyId.SHARED_ARTIFACT, ScaleTier.S1, seed=5)
    )
    known = {e["event_id"] for e in t.events}
    for e in t.events:
        for d in e["dependency_event_ids"]:
            assert d in known
        for a in e["output_artifact_ids"]:
            assert any(x["artifact_id"] == a for x in t.artifacts)


def test_ground_truth_isolation():
    gen = BenchmarkGenerator()
    t = gen.generate(
        BenchmarkConfig(
            ScenarioId.COMPLIANCE_REVIEW,
            TopologyId.SEQUENTIAL,
            ScaleTier.S1,
            seed=4,
            fault_types=(FaultType.INCORRECT_TOOL_OUTPUT.value,),
        )
    )
    events, arts = t.algorithm_inputs()
    blob = json.dumps({"events": events, "artifacts": arts})
    assert "intervention_id" not in blob
    assert "Ground truth records generator intent" not in blob
    assert t.ground_truth.interventions
    assert t.ground_truth.disclaimer


def test_fault_injection_each_type():
    gen = BenchmarkGenerator()
    for fault in FaultType:
        cfg = BenchmarkConfig(
            ScenarioId.FINANCIAL_LOAN,
            TopologyId.MIXED,
            ScaleTier.S1,
            seed=200 + list(FaultType).index(fault),
            fault_types=(fault.value,),
            incomplete=(fault == FaultType.INCOMPLETE_TRACE),
        )
        t = gen.generate(cfg)
        assert t.manifest.intervention_count >= 1
        assert any(i.fault_type == fault.value for i in t.ground_truth.interventions)
        v = validate_generated_trace(t, require_complete=False)
        assert v.ok, (fault, v.errors)


def test_incomplete_trace_marked():
    gen = BenchmarkGenerator()
    t = gen.generate(
        BenchmarkConfig(
            ScenarioId.FINANCIAL_LOAN,
            TopologyId.SEQUENTIAL,
            ScaleTier.S1,
            seed=3,
            incomplete=True,
            fault_types=(FaultType.INCOMPLETE_TRACE.value,),
        )
    )
    assert t.manifest.incomplete
    assert t.ground_truth.quality.intentionally_incomplete
    v = validate_generated_trace(t, require_complete=False)
    assert v.ok
    assert v.incomplete


def test_config_validation_fingerprint_stable():
    a = BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=1)
    b = BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=1)
    assert a.fingerprint() == b.fingerprint()
    c = BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=2)
    assert a.fingerprint() != c.fingerprint()


def test_assign_agents_stable():
    template = get_scenario(ScenarioId.FINANCIAL_LOAN)
    a1 = assign_agents(template, 5)
    a2 = assign_agents(template, 5)
    assert a1 == a2
    assert len(a1) == 5


def test_write_trace_separates_gt(tmp_path: Path):
    gen = BenchmarkGenerator()
    t = gen.generate(BenchmarkConfig(ScenarioId.FINANCIAL_LOAN, TopologyId.SEQUENTIAL, ScaleTier.S1, seed=1))
    paths = gen.write_trace(
        t,
        events_dir=tmp_path / "traces",
        ground_truth_dir=tmp_path / "gt",
        manifests_dir=tmp_path / "man",
    )
    assert paths["events"].exists()
    assert paths["ground_truth"].exists()
    events_blob = paths["events"].read_text(encoding="utf-8")
    assert "interventions" not in events_blob
