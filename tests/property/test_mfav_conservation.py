"""Property tests for MFAV factor conservation and exclusive mapping."""

from __future__ import annotations

import math
import random

import pytest

from agenttrust.accountability import MFAV, MFAVFactor, EventFactorClassifier
from agenttrust.attribution.rpa import RPAResult
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import EventCategory
from tests.conftest import make_artifact, make_event

CATEGORIES = [c.value for c in EventCategory]


def _synthetic_trace(rng: random.Random, n: int) -> ProvenanceTrace:
    events = []
    arts = []
    for i in range(n):
        cat = rng.choice(CATEGORIES)
        kwargs: dict = {
            "event_id": f"e{i}",
            "category": cat,
            "agent_id": f"agent-{rng.randint(0, 3)}" if rng.random() > 0.2 else None,
        }
        if cat == "reasoning" and rng.random() < 0.3:
            kwargs["model_id"] = f"model-{rng.randint(0, 2)}"
        if cat in ("tool", "transformation") and rng.random() < 0.5:
            kwargs["tool_id"] = f"tool-{rng.randint(0, 2)}"
        if cat in ("retrieval", "knowledge", "transformation") and rng.random() < 0.7:
            aid = f"art-{i}"
            kwargs["outputs"] = [aid]
            arts.append(make_artifact(aid, aid))
        if cat in ("retrieval", "knowledge") and rng.random() < 0.2:
            kwargs["metadata"] = {"subtype": "memory"}
        events.append(make_event(**kwargs))
    trace = ProvenanceTrace()
    trace.load_records(events, arts)
    return trace


def _rpa_from_alloc(alloc: dict[str, float], outcome_id: str = "O") -> RPAResult:
    total = sum(alloc.values())
    return RPAResult(
        outcome_id=outcome_id,
        projection_kind=ProjectionKind.P1_DIRECT.value,
        algorithm_name="conserved_backward_flow",
        algorithm_version="2.2.0",
        alpha=0.0,
        parent_allocation_policy="equal_parents",
        node_allocations=dict(alloc),
        root_allocations={k: v for k, v in alloc.items() if v},
        conservation={
            "sum_node_allocations": total,
            "abs_error_from_one_nodes": abs(total - 1.0),
        },
        completeness={"incomplete": False},
        cycle_diagnostics={"has_cycle": False},
        config={},
        reproducibility={},
    )


@pytest.mark.parametrize("seed", range(20))
def test_factor_sum_equals_event_sum(seed: int):
    rng = random.Random(seed)
    n = rng.randint(3, 12)
    trace = _synthetic_trace(rng, n)
    # Random non-negative allocations summing to 1
    weights = [rng.random() for _ in range(n)]
    s = sum(weights) or 1.0
    alloc = {f"e{i}": weights[i] / s for i in range(n)}
    profile = MFAV().compute(_rpa_from_alloc(alloc), trace=trace)
    event_sum = sum(alloc.values())
    factor_sum = sum(profile.raw_factor_allocations.values())
    assert math.isclose(factor_sum, event_sum, abs_tol=1e-12)
    assert profile.normalized_factor_vector is not None
    assert math.isclose(sum(profile.normalized_factor_vector.values()), 1.0, abs_tol=1e-12)


@pytest.mark.parametrize("seed", range(15))
def test_every_allocation_maps_to_exactly_one_factor(seed: int):
    rng = random.Random(1000 + seed)
    n = rng.randint(2, 10)
    trace = _synthetic_trace(rng, n)
    weights = [rng.random() + 0.01 for _ in range(n)]
    s = sum(weights)
    alloc = {f"e{i}": weights[i] / s for i in range(n)}
    profile = MFAV().compute(_rpa_from_alloc(alloc), trace=trace)
    assigned = {a.event_id: a.factor for a in profile.event_assignments}
    assert set(assigned) == {k for k, v in alloc.items() if v != 0.0}
    assert all(f in {x.value for x in MFAVFactor} for f in assigned.values())
    # Exclusive: one assignment row per event
    assert len(profile.event_assignments) == len(assigned)


def test_classifier_exclusive_over_all_categories():
    clf = EventFactorClassifier()
    for cat in EventCategory:
        events = [make_event("e1", category=cat.value, agent_id="A")]
        trace = ProvenanceTrace()
        trace.load_records(events, [])
        c = clf.classify(trace.events[0])
        assert c.factor in MFAVFactor
