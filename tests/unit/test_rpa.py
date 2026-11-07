"""Conserved RPA unit tests."""

from __future__ import annotations

import math

import networkx as nx
import pytest

from agenttrust.attribution.rpa import ConservedRPA, ParentAllocationPolicy, RPAConfig, RPAError
from agenttrust.mlpg.projections import AttributionProjection, ProjectionKind, ProjectedEdge
from agenttrust.provenance_trace import ProvenanceTrace
from tests.conftest import make_artifact, make_event


def _proj_from_edges(nodes: list[str], edges: list[tuple[str, str]], kind=ProjectionKind.P1_DIRECT):
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n, node_kind="EVENT")
    projected = []
    for u, v in edges:
        g.add_edge(u, v, derived=False, origin="DEPENDS_ON", evidence_path=[u, v])
        projected.append(
            ProjectedEdge(u, v, derived=False, evidence_path=(u, v), origin="DEPENDS_ON")
        )
    return AttributionProjection(kind=kind, graph=g, edges=projected)


def test_single_outcome_one_root():
    # A -> O
    p = _proj_from_edges(["A", "O"], [("A", "O")])
    r = ConservedRPA().allocate(p, "O")
    assert math.isclose(r.node_allocations["A"], 1.0)
    assert math.isclose(r.node_allocations["O"], 0.0)
    assert math.isclose(sum(r.node_allocations.values()), 1.0)
    assert math.isclose(sum(r.root_allocations.values()), 1.0)


def test_linear_chain():
    # A -> B -> C
    p = _proj_from_edges(["A", "B", "C"], [("A", "B"), ("B", "C")])
    r = ConservedRPA().allocate(p, "C", config=RPAConfig(alpha=0.0))
    assert math.isclose(r.node_allocations["A"], 1.0)
    assert math.isclose(r.node_allocations["B"], 0.0)
    assert math.isclose(r.node_allocations["C"], 0.0)


def test_branching_multiple_parents():
    # A -> C, B -> C
    p = _proj_from_edges(["A", "B", "C"], [("A", "C"), ("B", "C")])
    r = ConservedRPA().allocate(p, "C")
    assert math.isclose(r.node_allocations["A"], 0.5)
    assert math.isclose(r.node_allocations["B"], 0.5)


def test_multiple_root_contributors_shared_ancestor():
    # A -> B, A -> C, B -> D, C -> D
    p = _proj_from_edges(
        ["A", "B", "C", "D"],
        [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
    )
    r = ConservedRPA().allocate(p, "D")
    assert math.isclose(r.node_allocations["A"], 1.0)
    assert math.isclose(sum(r.node_allocations.values()), 1.0)


def test_multiple_independent_outcomes():
    p = _proj_from_edges(
        ["A", "B", "O1", "O2"],
        [("A", "O1"), ("B", "O2")],
    )
    results = ConservedRPA().allocate_many(p, ["O1", "O2"])
    assert len(results) == 2
    assert math.isclose(results[0].node_allocations["A"], 1.0)
    assert math.isclose(results[0].node_allocations["B"], 0.0)
    assert math.isclose(results[1].node_allocations["B"], 1.0)
    assert math.isclose(results[1].node_allocations["A"], 0.0)


def test_disconnected_nodes_zero():
    p = _proj_from_edges(["A", "O", "Z"], [("A", "O")])
    r = ConservedRPA().allocate(p, "O")
    assert r.node_allocations["Z"] == 0.0
    assert math.isclose(sum(r.node_allocations.values()), 1.0)


def test_cycle_rejected():
    g = nx.DiGraph()
    g.add_nodes_from(["A", "B"])
    g.add_edge("A", "B")
    g.add_edge("B", "A")
    p = AttributionProjection(ProjectionKind.P1_DIRECT, g, [])
    with pytest.raises(RPAError, match="cycle"):
        ConservedRPA().allocate(p, "A")


def test_incomplete_trace_rejected_and_override():
    from agenttrust.provenance_trace import TraceCompleteness

    p = _proj_from_edges(["A", "O"], [("A", "O")])
    incomplete = TraceCompleteness(
        incomplete=True,
        has_dependency_cycle=False,
        suitable_for_dag_attribution=True,
        missing_dependency_parents=("missing",),
    )
    with pytest.raises(RPAError, match="incomplete"):
        ConservedRPA().allocate(p, "O", completeness=incomplete)
    r = ConservedRPA().allocate(
        p,
        "O",
        completeness=incomplete,
        config=RPAConfig(allow_incomplete=True),
    )
    assert "incomplete_trace" in r.overridden_guards


def test_deterministic_and_order_invariant():
    edges = [("A", "B"), ("B", "C"), ("A", "C")]
    p1 = _proj_from_edges(["A", "B", "C"], edges)
    p2 = _proj_from_edges(["C", "B", "A"], list(reversed(edges)))
    r1 = ConservedRPA().allocate(p1, "C")
    r2 = ConservedRPA().allocate(p2, "C")
    assert r1.node_allocations == r2.node_allocations


def test_no_negative_or_nan():
    p = _proj_from_edges(["A", "B", "C"], [("A", "B"), ("B", "C"), ("A", "C")])
    r = ConservedRPA().allocate(p, "C")
    for v in r.node_allocations.values():
        assert v >= 0.0
        assert not math.isnan(v)


def test_alpha_boundary_retain_all_at_outcome():
    p = _proj_from_edges(["A", "O"], [("A", "O")])
    r = ConservedRPA().allocate(p, "O", config=RPAConfig(alpha=1.0))
    # alpha=1: outcome retains all mass; nothing forwarded
    assert math.isclose(r.node_allocations["O"], 1.0)
    assert math.isclose(r.node_allocations["A"], 0.0)
    assert math.isclose(sum(r.node_allocations.values()), 1.0)


def test_p1_vs_p2_difference():
    arts = [make_artifact("ax", "bridge")]
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", inputs=["ax"]),  # no explicit DEPENDS_ON
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    before = trace.fingerprint()
    engine = ConservedRPA()
    # P1 has no edge e1->e2; e2 is its own root → allocation all on e2
    p1 = trace.project(ProjectionKind.P1_DIRECT)
    r1 = engine.allocate(p1, "e2", completeness=trace.completeness())
    assert math.isclose(r1.node_allocations["e2"], 1.0)

    p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    r2 = engine.allocate(p2, "e2", completeness=trace.completeness())
    assert math.isclose(r2.node_allocations["e1"], 1.0)
    assert math.isclose(r2.node_allocations["e2"], 0.0)
    assert trace.fingerprint() == before


def test_allocate_from_trace_on_processed_sample():
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    events = json.loads((repo / "data" / "processed" / "events_v2.json").read_text())["events"]
    arts = json.loads((repo / "data" / "processed" / "artifacts_v2.json").read_text())["artifacts"]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    fp = trace.fingerprint()
    results = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)
    assert len(results) == 1
    r = results[0]
    assert math.isclose(sum(r.node_allocations.values()), 1.0, abs_tol=1e-12)
    assert math.isclose(sum(r.root_allocations.values()), 1.0, abs_tol=1e-12)
    assert r.alpha == 0.0
    assert r.parent_allocation_policy == ParentAllocationPolicy.EQUAL_PARENTS.value
    assert trace.fingerprint() == fp
