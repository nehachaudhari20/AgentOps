"""Phase 2.3 MFAV unit tests."""

from __future__ import annotations

import copy
import math

import pytest

from agenttrust.accountability import (
    MFAV,
    MFAVError,
    MFAVFactor,
    MFAVStatus,
    EventFactorClassifier,
    UNIDENTIFIED_ENTITY_KEY,
)
from agenttrust.attribution.rpa import ConservedRPA, RPAResult
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import EventCategory
from agenttrust.schema.event import EventRecord
from tests.conftest import make_artifact, make_event


def _load_one(eid: str, events: list, arts: list) -> EventRecord:
    trace = ProvenanceTrace()
    # Ensure artifacts cover ids referenced
    seen = {a["artifact_id"] for a in arts}
    for ev in events:
        for aid in ev.get("input_artifact_ids", []) + ev.get("output_artifact_ids", []):
            if aid not in seen:
                arts.append(make_artifact(aid, aid))
                seen.add(aid)
    trace.load_records(events, arts)
    return next(e for e in trace.events if e.event_id == eid)


def _rpa(
    allocations: dict[str, float],
    *,
    outcome_id: str = "O",
    projection_kind: str = ProjectionKind.P1_DIRECT.value,
    incomplete: bool = False,
    overridden: list[str] | None = None,
    warnings: list[str] | None = None,
    alpha: float = 0.0,
) -> RPAResult:
    total = sum(allocations.values())
    return RPAResult(
        outcome_id=outcome_id,
        projection_kind=projection_kind,
        algorithm_name="conserved_backward_flow",
        algorithm_version="2.2.0",
        alpha=alpha,
        parent_allocation_policy="equal_parents",
        node_allocations=dict(allocations),
        root_allocations={k: v for k, v in allocations.items() if v},
        conservation={
            "sum_node_allocations": total,
            "sum_root_allocations": total,
            "abs_error_from_one_nodes": abs(total - 1.0),
            "abs_error_from_one_roots": abs(total - 1.0),
        },
        completeness={
            "incomplete": incomplete,
            "has_dependency_cycle": False,
            "suitable_for_dag_attribution": not incomplete,
            "missing_dependency_parents": [],
        },
        cycle_diagnostics={"has_cycle": False, "cycle_nodes": None},
        config={"alpha": alpha, "parent_policy": "equal_parents", "allow_incomplete": incomplete},
        reproducibility={"outcome_id": outcome_id},
        warnings=list(warnings or []),
        overridden_guards=list(overridden or []),
    )


def _trace_for(*specs: dict) -> ProvenanceTrace:
    events = []
    arts: list[dict] = []
    seen: set[str] = set()
    for spec in specs:
        ev = make_event(**spec)
        events.append(ev)
        for aid in ev.get("input_artifact_ids", []) + ev.get("output_artifact_ids", []):
            if aid not in seen:
                arts.append(make_artifact(aid, aid))
                seen.add(aid)
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    return trace


# --- Classification ---


@pytest.mark.parametrize(
    "category,expected",
    [
        ("instruction", MFAVFactor.PROMPT),
        ("reasoning", MFAVFactor.AGENT),
        ("retrieval", MFAVFactor.DATA),
        ("knowledge", MFAVFactor.DATA),
        ("transformation", MFAVFactor.DATA),
        ("tool", MFAVFactor.TOOL),
        ("decision", MFAVFactor.EXECUTION),
        ("other", MFAVFactor.OTHER),
    ],
)
def test_primary_factor_classification(category, expected):
    ev = _load_one(
        "e1",
        [make_event("e1", event_type="custom", category=category, agent_id="A1")],
        [],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == expected


def test_unknown_category_maps_to_other():
    ev = _load_one("e1", [make_event("e1", event_type="weird_xyz")], [])
    assert ev.category == EventCategory.OTHER
    assert EventFactorClassifier().classify(ev).factor == MFAVFactor.OTHER


def test_explicit_agent_identity():
    ev = _load_one("e1", [make_event("e1", category="reasoning", agent_id="agent-42")], [])
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.AGENT
    assert c.entity_id == "agent-42"
    assert not c.unidentified


def test_explicit_model_identity():
    ev = _load_one(
        "e1",
        [make_event("e1", category="reasoning", agent_id="A1", model_id="gpt-test")],
        [],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.MODEL
    assert c.entity_id == "gpt-test"
    assert c.entity_kind == "model"


def test_missing_model_identity_stays_agent():
    ev = _load_one(
        "e1",
        [make_event("e1", category="reasoning", agent_id="Reasoner")],
        [],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.AGENT
    assert c.entity_id == "Reasoner"


def test_tool_identity():
    ev = _load_one(
        "e1",
        [make_event("e1", category="tool", event_type="tool_call", tool_id="calc-v1")],
        [],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.TOOL
    assert c.entity_id == "calc-v1"


def test_transformation_with_tool_id_maps_to_tool():
    ev = _load_one(
        "e1",
        [make_event("e1", category="transformation", tool_id="embedder")],
        [],
    )
    assert EventFactorClassifier().classify(ev).factor == MFAVFactor.TOOL


def test_artifact_data_identity():
    ev = _load_one(
        "e1",
        [make_event("e1", category="retrieval", outputs=["art-9"], agent_id="R")],
        [make_artifact("art-9", "doc")],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.DATA
    assert c.entity_id == "art-9"
    assert c.entity_kind == "artifact"


def test_prompt_identity_uses_event_id():
    ev = _load_one(
        "prompt-1",
        [make_event("prompt-1", category="instruction", event_type="prompt")],
        [],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.PROMPT
    assert c.entity_id == "prompt-1"


def test_execution_classification():
    ev = _load_one(
        "d1",
        [make_event("d1", category="decision", event_type="action")],
        [],
    )
    assert EventFactorClassifier().classify(ev).factor == MFAVFactor.EXECUTION


def test_explicit_memory_subtype():
    ev = _load_one(
        "e1",
        [
            make_event(
                "e1",
                category="retrieval",
                outputs=["m1"],
                metadata={"subtype": "memory"},
            )
        ],
        [make_artifact("m1", "mem")],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.DATA
    assert "memory" in c.secondary_subtypes


def test_memory_not_inferred_from_agent_display_name():
    ev = _load_one(
        "e1",
        [make_event("e1", category="retrieval", agent_id="Memory", outputs=["a1"])],
        [make_artifact("a1", "x")],
    )
    c = EventFactorClassifier().classify(ev)
    assert c.factor == MFAVFactor.DATA
    assert "memory" not in c.secondary_subtypes
    assert any("Memory" in w for w in c.warnings)


def test_exclusive_classification_one_factor():
    clf = EventFactorClassifier()
    for cat in EventCategory:
        ev = _load_one("e1", [make_event("e1", category=cat.value)], [])
        c = clf.classify(ev)
        assert isinstance(c.factor, MFAVFactor)


# --- Aggregation ---


def test_hand_calculated_example():
    """Agent 0.40, tool 0.35, data 0.25 → identical normalized vector."""
    trace = _trace_for(
        {"event_id": "ea", "category": "reasoning", "agent_id": "A"},
        {"event_id": "et", "category": "tool", "event_type": "tool_call", "tool_id": "T"},
        {"event_id": "ed", "category": "retrieval", "outputs": ["d1"]},
    )
    rpa = _rpa({"ea": 0.40, "et": 0.35, "ed": 0.25})
    profile = MFAV().compute(rpa, trace=trace)
    assert math.isclose(profile.raw_factor_allocations["agent"], 0.40)
    assert math.isclose(profile.raw_factor_allocations["tool"], 0.35)
    assert math.isclose(profile.raw_factor_allocations["data"], 0.25)
    for f in ("model", "prompt", "execution", "other"):
        assert profile.raw_factor_allocations[f] == 0.0
    assert profile.normalized_factor_vector is not None
    assert math.isclose(sum(profile.normalized_factor_vector.values()), 1.0)
    assert math.isclose(profile.normalized_factor_vector["agent"], 0.40)


def test_no_double_counting_multiple_events_one_factor():
    trace = _trace_for(
        {"event_id": "a1", "category": "reasoning", "agent_id": "A"},
        {"event_id": "a2", "category": "reasoning", "agent_id": "A"},
    )
    rpa = _rpa({"a1": 0.3, "a2": 0.7})
    profile = MFAV().compute(rpa, trace=trace)
    assert math.isclose(profile.raw_factor_allocations["agent"], 1.0)
    assert len([a for a in profile.event_assignments if a.factor == "agent"]) == 2
    assert math.isclose(sum(a.allocation for a in profile.event_assignments), 1.0)


def test_multiple_entities_within_factor():
    trace = _trace_for(
        {"event_id": "t1", "category": "tool", "tool_id": "tool-a"},
        {"event_id": "t2", "category": "tool", "tool_id": "tool-b"},
    )
    rpa = _rpa({"t1": 0.25, "t2": 0.75})
    profile = MFAV().compute(rpa, trace=trace)
    entities = {e.entity_id: e.allocation for e in profile.entity_contributions if e.factor == "tool"}
    assert math.isclose(entities["tool-a"], 0.25)
    assert math.isclose(entities["tool-b"], 0.75)


def test_same_display_name_different_stable_ids():
    # agent_id is the stable id; same "display" isn't used — two distinct agent ids
    trace = _trace_for(
        {"event_id": "e1", "category": "reasoning", "agent_id": "AgentX"},
        {"event_id": "e2", "category": "reasoning", "agent_id": "AgentX-2"},
    )
    # Simulate two agents that might share a display label elsewhere but have distinct IDs
    rpa = _rpa({"e1": 0.5, "e2": 0.5})
    profile = MFAV().compute(rpa, trace=trace)
    ids = {e.entity_id for e in profile.entity_contributions if e.factor == "agent"}
    assert ids == {"AgentX", "AgentX-2"}


def test_unidentified_entity_contributions():
    trace = _trace_for(
        {"event_id": "e1", "category": "reasoning", "agent_id": None},
        {"event_id": "e2", "category": "retrieval"},  # no artifacts
    )
    rpa = _rpa({"e1": 0.6, "e2": 0.4})
    profile = MFAV().compute(rpa, trace=trace)
    assert any(u.factor == "agent" and u.unidentified for u in profile.unidentified_contributions)
    assert any(u.factor == "data" and u.unidentified for u in profile.unidentified_contributions)
    assert all(u.entity_id == UNIDENTIFIED_ENTITY_KEY for u in profile.unidentified_contributions)


def test_zero_allocation():
    trace = _trace_for({"event_id": "e1", "category": "reasoning", "agent_id": "A"})
    rpa = _rpa({"e1": 0.0})
    profile = MFAV().compute(rpa, trace=trace)
    assert profile.status == MFAVStatus.ZERO_ALLOCATION
    assert profile.normalized_factor_vector is None
    assert profile.total_raw_allocation == 0.0
    assert not profile.complete


def test_invalid_negative_allocation():
    trace = _trace_for({"event_id": "e1", "category": "reasoning", "agent_id": "A"})
    rpa = _rpa({"e1": -0.1})
    with pytest.raises(MFAVError, match="Invalid RPA allocation"):
        MFAV().compute(rpa, trace=trace)


def test_nan_and_infinite_allocation_rejection():
    trace = _trace_for({"event_id": "e1", "category": "reasoning", "agent_id": "A"})
    with pytest.raises(MFAVError):
        MFAV().compute(_rpa({"e1": float("nan")}), trace=trace)
    with pytest.raises(MFAVError):
        MFAV().compute(_rpa({"e1": float("inf")}), trace=trace)


def test_conservation_of_raw_and_normalized():
    trace = _trace_for(
        {"event_id": "a", "category": "reasoning", "agent_id": "A"},
        {"event_id": "p", "category": "instruction"},
        {"event_id": "x", "category": "decision"},
    )
    alloc = {"a": 0.2, "p": 0.3, "x": 0.5}
    profile = MFAV().compute(_rpa(alloc), trace=trace)
    assert math.isclose(sum(profile.raw_factor_allocations.values()), sum(alloc.values()))
    assert profile.normalized_factor_vector is not None
    assert math.isclose(sum(profile.normalized_factor_vector.values()), 1.0, abs_tol=1e-12)
    assert profile.conservation_error <= 1e-12


def test_incomplete_rpa_result_propagation():
    trace = _trace_for({"event_id": "e1", "category": "reasoning", "agent_id": "A"})
    rpa = _rpa({"e1": 1.0}, incomplete=True, overridden=["incomplete_trace"], warnings=["warn"])
    profile = MFAV().compute(rpa, trace=trace)
    assert profile.status == MFAVStatus.OVERRIDDEN
    assert not profile.complete
    assert "incomplete_trace" in profile.overridden_guards
    assert "warn" in profile.rpa_warnings


def test_multiple_independent_outcomes():
    trace = _trace_for(
        {"event_id": "a", "category": "reasoning", "agent_id": "A"},
        {"event_id": "b", "category": "tool", "tool_id": "T"},
    )
    r1 = _rpa({"a": 1.0}, outcome_id="O1")
    r2 = _rpa({"b": 1.0}, outcome_id="O2")
    profiles = MFAV().compute_many([r1, r2], trace=trace)
    assert profiles[0].outcome_id == "O1"
    assert math.isclose(profiles[0].raw_factor_allocations["agent"], 1.0)
    assert profiles[1].outcome_id == "O2"
    assert math.isclose(profiles[1].raw_factor_allocations["tool"], 1.0)


def test_p1_p2_result_distinction():
    arts = [make_artifact("ax", "bridge")]
    events = [
        make_event("e1", category="reasoning", outputs=["ax"]),
        make_event("e2", category="decision", event_type="action", inputs=["ax"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    engine = ConservedRPA()
    p1 = engine.allocate(
        trace.project(ProjectionKind.P1_DIRECT),
        "e2",
        completeness=trace.completeness(),
    )
    p2 = engine.allocate(
        trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE),
        "e2",
        completeness=trace.completeness(),
    )
    m1 = MFAV().compute(p1, trace=trace)
    m2 = MFAV().compute(p2, trace=trace)
    assert m1.projection_kind != m2.projection_kind
    assert m1.to_dict() != m2.to_dict()


def test_deterministic_output():
    trace = _trace_for(
        {"event_id": "z", "category": "other"},
        {"event_id": "a", "category": "reasoning", "agent_id": "A"},
    )
    rpa = _rpa({"a": 0.6, "z": 0.4})
    d1 = MFAV().compute(rpa, trace=trace).to_dict()
    d2 = MFAV().compute(rpa, trace=trace).to_dict()
    assert d1 == d2


def test_serialization_roundtrip_dict():
    trace = _trace_for({"event_id": "e1", "category": "tool", "tool_id": "T1"})
    profile = MFAV().compute(_rpa({"e1": 1.0}), trace=trace)
    d = profile.to_dict()
    assert d["mfav_algorithm_version"] == "2.3.0"
    assert d["normalized_factor_vector"]["tool"] == 1.0
    assert isinstance(d["entity_contributions"], list)


def test_no_mutation_of_rpa_or_graph():
    arts = [make_artifact("ax", "x")]
    events = [
        make_event("e1", category="reasoning", outputs=["ax"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    fp = trace.fingerprint()
    rpa = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)[0]
    before = copy.deepcopy(rpa.to_dict())
    MFAV().compute(rpa, trace=trace)
    assert rpa.to_dict() == before
    assert trace.fingerprint() == fp


def test_model_not_inferred_from_agent_name():
    trace = _trace_for(
        {"event_id": "e1", "category": "reasoning", "agent_id": "gpt-4-lookalike"},
    )
    profile = MFAV().compute(_rpa({"e1": 1.0}), trace=trace)
    assert profile.raw_factor_allocations["model"] == 0.0
    assert math.isclose(profile.raw_factor_allocations["agent"], 1.0)


def test_secondary_memory_not_in_primary_totals():
    trace = _trace_for(
        {
            "event_id": "e1",
            "category": "knowledge",
            "outputs": ["doc1"],
            "metadata": {"memory": "true"},
        }
    )
    profile = MFAV().compute(_rpa({"e1": 1.0}), trace=trace)
    assert math.isclose(profile.raw_factor_allocations["data"], 1.0)
    assert "memory" not in profile.raw_factor_allocations
    assert math.isclose(profile.secondary_subtype_totals["memory"], 1.0)


def test_optional_model_id_schema_backward_compatible():
    # Historical-style record without model_id still validates
    trace = ProvenanceTrace()
    report = trace.load_records([make_event("e1", category="reasoning")], [])
    assert len(report.accepted_event_ids) == 1
    assert trace.events[0].model_id is None


def test_end_to_end_api_with_rpa():
    events = [
        make_event("root", category="reasoning", agent_id="A"),
        make_event("out", category="decision", event_type="action", deps=["root"]),
    ]
    trace = ProvenanceTrace()
    trace.load_records(events, [])
    rpa_results = ConservedRPA().allocate_from_trace(
        trace, projection_kind=ProjectionKind.P1_DIRECT
    )
    profiles = [MFAV().compute(r, trace=trace) for r in rpa_results]
    assert len(profiles) == 1
    assert math.isclose(profiles[0].raw_factor_allocations["agent"], 1.0)
    assert profiles[0].complete
