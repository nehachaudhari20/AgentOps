"""MLPG graph construction tests."""

from __future__ import annotations

from agenttrust.mlpg.graph_builder import graph_fingerprint
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import NodeKind, RelationshipType
from tests.conftest import make_artifact, make_event


def _load_simple():
    arts = [make_artifact("a_in", "in"), make_artifact("a_out", "out")]
    events = [
        make_event("e1", event_type="prompt", outputs=["a_out"], inputs=[]),
        make_event(
            "e2",
            event_type="reasoning",
            deps=["e1"],
            inputs=["a_out"],
            outputs=["a_in"],
        ),
    ]
    # fix: e2 consumes a_out produces a_in
    trace = ProvenanceTrace()
    report = trace.load_records(events, arts)
    return trace, report


def test_event_and_artifact_nodes():
    trace, _ = _load_simple()
    g = trace.graph
    assert g.nodes["e1"]["node_kind"] == NodeKind.EVENT.value
    assert g.nodes["a_out"]["node_kind"] == NodeKind.ARTIFACT.value


def test_produces_direction():
    trace, _ = _load_simple()
    g = trace.graph
    assert g.has_edge("e1", "a_out")
    data = g.get_edge_data("e1", "a_out")
    assert RelationshipType.PRODUCES.value in data


def test_consumes_direction():
    trace, _ = _load_simple()
    g = trace.graph
    assert g.has_edge("a_out", "e2")
    data = g.get_edge_data("a_out", "e2")
    assert RelationshipType.CONSUMES.value in data


def test_depends_on_direction():
    trace, _ = _load_simple()
    g = trace.graph
    # upstream e1 → dependent e2
    assert g.has_edge("e1", "e2")
    data = g.get_edge_data("e1", "e2")
    assert RelationshipType.DEPENDS_ON.value in data


def test_invokes_and_retries():
    arts = [make_artifact("a1")]
    events = [
        make_event("orig", event_type="tool_call", outputs=["a1"]),
        make_event(
            "retry",
            event_type="tool_call",
            outputs=["a1"],
            retries_event_id="orig",
            invokes_event_ids=["orig"],
        ),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    g = trace.graph
    assert RelationshipType.RETRIES.value in g.get_edge_data("retry", "orig")
    assert RelationshipType.INVOKES.value in g.get_edge_data("retry", "orig")


def test_observed_after_not_auto_from_timestamps():
    arts = []
    events = [
        make_event("e1", ts_start="2024-01-01T00:00:00Z", ts_end="2024-01-01T00:00:01Z"),
        make_event("e2", ts_start="2024-01-01T00:00:02Z", ts_end="2024-01-01T00:00:03Z"),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    g = trace.graph
    # No OBSERVED_AFTER unless explicitly provided
    for u, v, k, d in g.edges(keys=True, data=True):
        assert d.get("rel_type") != RelationshipType.OBSERVED_AFTER.value


def test_explicit_observed_after():
    events = [
        make_event("e1"),
        make_event("e2", observed_after_event_ids=["e1"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, [])
    g = trace.graph
    assert RelationshipType.OBSERVED_AFTER.value in g.get_edge_data("e1", "e2")


def test_missing_dependency_parent_flagged():
    events = [make_event("e1", deps=["missing-parent"])]
    trace = ProvenanceTrace()
    report = trace.load_records(events, [])
    assert report.incomplete is True
    assert "missing-parent" in report.missing_dependency_parents
    assert "e1" in report.accepted_event_ids


def test_self_dependency_rejected():
    events = [make_event("e1", deps=["e1"])]
    trace = ProvenanceTrace()
    report = trace.load_records(events, [])
    assert "e1" in report.quarantined_event_ids
    assert any(d.code == "self_dependency" for d in report.diagnostics)


def test_cycle_detected():
    events = [
        make_event("e1", deps=["e2"]),
        make_event("e2", deps=["e1"]),
    ]
    trace = ProvenanceTrace()
    report = trace.load_records(events, [])
    assert report.has_dependency_cycle is True
    assert report.suitable_for_dag_attribution is False


def test_repeated_loading_does_not_duplicate():
    events = [make_event("e1")]
    trace = ProvenanceTrace()
    trace.load_records(events, [])
    n1 = trace.graph.number_of_nodes()
    trace.load_records(events, [], replace=True)
    n2 = trace.graph.number_of_nodes()
    assert n1 == n2 == 1


def test_deterministic_graph_construction():
    arts = [make_artifact("a1"), make_artifact("a2")]
    events = [
        make_event("e2", deps=["e1"], inputs=["a1"], outputs=["a2"]),
        make_event("e1", outputs=["a1"]),
    ]
    t1 = ProvenanceTrace()
    t1.load_records(events, arts)
    t2 = ProvenanceTrace()
    t2.load_records(list(reversed(events)), list(reversed(arts)))
    assert t1.fingerprint() == t2.fingerprint()


def test_no_edge_weights():
    trace, _ = _load_simple()
    for _, _, _, d in trace.graph.edges(keys=True, data=True):
        assert "weight" not in d
