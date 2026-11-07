"""P1/P2 attribution projection tests."""

from __future__ import annotations

from agenttrust.mlpg.graph_builder import graph_fingerprint
from agenttrust.mlpg.projections import ProjectionKind, snapshot_edge_set
from agenttrust.provenance_trace import ProvenanceTrace
from tests.conftest import make_artifact, make_event


def test_p1_only_explicit_depends_on():
    arts = [
        make_artifact("ax", "x"),
        make_artifact("ay", "y"),
    ]
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", deps=["e1"], inputs=["ax"], outputs=["ay"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    p1 = trace.project(ProjectionKind.P1_DIRECT)
    assert p1.graph.number_of_edges() == 1
    assert p1.graph.has_edge("e1", "e2")
    assert all(not e.derived for e in p1.edges)
    assert all(e.origin == "DEPENDS_ON" for e in p1.edges)


def test_p2_includes_artifact_bridge():
    arts = [make_artifact("ax", "x")]
    # No explicit DEPENDS_ON between e1 and e2 — only artifact bridge
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", inputs=["ax"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    p1 = trace.project(ProjectionKind.P1_DIRECT)
    p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p1.graph.number_of_edges() == 0
    assert p2.graph.has_edge("e1", "e2")
    bridge = [e for e in p2.edges if e.origin == "ARTIFACT_BRIDGE"]
    assert len(bridge) == 1
    assert bridge[0].derived is True
    assert bridge[0].evidence_path == ("e1", "ax", "e2")


def test_p2_labels_derived_edges():
    arts = [make_artifact("ax", "x")]
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", inputs=["ax"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p2.graph["e1"]["e2"]["derived"] is True


def test_no_double_count_explicit_and_bridge():
    arts = [make_artifact("ax", "x")]
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", deps=["e1"], inputs=["ax"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p2.graph.number_of_edges() == 1
    assert p2.edges[0].origin == "DEPENDS_ON"
    assert p2.edges[0].derived is False


def test_unverified_artifact_bridge_excluded():
    # Artifact without content_hash should not appear in accepted artifacts;
    # simulate by omitting artifact from load while referencing id → incomplete, no bridge.
    events = [
        make_event("e1", outputs=["missing_art"]),
        make_event("e2", inputs=["missing_art"]),
    ]
    trace = ProvenanceTrace()
    report = trace.load_records(events, artifacts=[])
    assert report.incomplete is True
    p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p2.graph.number_of_edges() == 0


def test_projection_does_not_mutate_original_graph():
    arts = [make_artifact("ax", "x")]
    events = [
        make_event("e1", outputs=["ax"]),
        make_event("e2", inputs=["ax"], deps=["e1"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    before_fp = graph_fingerprint(trace.graph)
    before_edges = snapshot_edge_set(trace.graph)
    _ = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert graph_fingerprint(trace.graph) == before_fp
    assert snapshot_edge_set(trace.graph) == before_edges
