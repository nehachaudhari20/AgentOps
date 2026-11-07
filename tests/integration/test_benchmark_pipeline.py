"""Integration: generated benchmarks load into ProvenanceTrace → RPA → MFAV."""

from __future__ import annotations

import pytest

from agenttrust import ConservedRPA, MFAV, ProvenanceTrace
from agenttrust.benchmark import (
    BenchmarkConfig,
    BenchmarkGenerator,
    ScenarioId,
    ScaleTier,
    TopologyId,
    validate_generated_trace,
)
from agenttrust.mlpg.projections import ProjectionKind


@pytest.mark.parametrize("topology", list(TopologyId))
def test_complete_trace_pipeline(topology: TopologyId):
    gen = BenchmarkGenerator()
    cfg = BenchmarkConfig(
        scenario_id=ScenarioId.FINANCIAL_LOAN,
        topology_id=topology,
        scale_tier=ScaleTier.S1,
        seed=17,
    )
    trace_pkg = gen.generate(cfg)
    v = validate_generated_trace(trace_pkg, require_complete=True)
    assert v.ok, v.errors

    pt = ProvenanceTrace()
    report = pt.load_records(*trace_pkg.algorithm_inputs())
    assert len(report.accepted_event_ids) == len(trace_pkg.events)
    before = pt.fingerprint()

    p1 = pt.project(ProjectionKind.P1_DIRECT)
    p2 = pt.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p1.graph.number_of_nodes() >= 1
    assert p2.graph.number_of_nodes() >= 1

    rpa_results = ConservedRPA().allocate_from_trace(pt, projection_kind=ProjectionKind.P1_DIRECT)
    assert rpa_results
    profiles = [MFAV().compute(r, trace=pt) for r in rpa_results]
    assert len(profiles) == len(rpa_results)
    assert pt.fingerprint() == before


def test_incomplete_trace_loads_but_rpa_guarded():
    from agenttrust.attribution.rpa import RPAConfig, RPAError

    gen = BenchmarkGenerator()
    from agenttrust.benchmark import FaultType

    pkg = gen.generate(
        BenchmarkConfig(
            ScenarioId.FRAUD_INVESTIGATION,
            TopologyId.SEQUENTIAL,
            ScaleTier.S1,
            seed=9,
            incomplete=True,
            fault_types=(FaultType.MISSING_DEPENDENCY.value,),
        )
    )
    pt = ProvenanceTrace()
    pt.load_records(*pkg.algorithm_inputs())
    assert pt.completeness().incomplete
    with pytest.raises(RPAError):
        ConservedRPA().allocate_from_trace(pt, projection_kind=ProjectionKind.P1_DIRECT)
    # Override path still works and MFAV can consume marked result
    results = ConservedRPA().allocate_from_trace(
        pt,
        projection_kind=ProjectionKind.P1_DIRECT,
        config=RPAConfig(allow_incomplete=True),
    )
    assert results[0].overridden_guards
    profile = MFAV().compute(results[0], trace=pt)
    assert not profile.complete
