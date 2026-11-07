"""Phase 2.10 baselines, metrics, PLHC attacks, GT separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrust.evaluation.baselines import (
    MARKOV_STATUS,
    allocate_b0_uniform,
    allocate_b1_last_touch,
    allocate_b2_p1_equal_share,
    allocate_b4_shapley,
    allocate_rpa,
)
from agenttrust.evaluation.metrics import (
    cliffs_delta,
    edge_prf,
    holm_correct,
    mae,
    mean_ci_bootstrap,
    paired_mean_diff_ci,
    rmse,
    spearman,
    top_k_agreement,
)
from agenttrust.evaluation.plhc_attacks import evaluate_plhc_attacks
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from tests.conftest import make_artifact, make_event


def _trace():
    events = [
        make_event(
            "e1",
            category="reasoning",
            agent_id="A",
            outputs=["a1"],
            ts_start="2024-01-01T00:00:00Z",
            ts_end="2024-01-01T00:00:01Z",
        ),
        make_event(
            "e2",
            category="decision",
            event_type="action",
            agent_id="B",
            deps=["e1"],
            inputs=["a1"],
            ts_start="2024-01-01T00:00:10Z",
            ts_end="2024-01-01T00:00:11Z",
        ),
    ]
    arts = [make_artifact("a1")]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    assert "e2" in t.validation_report.accepted_event_ids
    return t


def test_mae_rmse_normalization_universe():
    pred = {"A": 1.0}
    truth = {"A": 0.5, "B": 0.5}
    assert abs(mae(pred, truth) - (0.5 + 0.5) / 2) < 1e-12
    assert rmse(pred, truth) > 0
    assert top_k_agreement({"A": 1.0}, {"A": 1.0}, k=1) == 1.0


def test_spearman_and_empty():
    import math

    assert abs(spearman({"A": 0.0, "B": 1.0}, {"A": 0.0, "B": 1.0}) - 1.0) < 1e-9
    assert math.isnan(mae({}, {}))


def test_b0_b1_rpa_determinism():
    t = _trace()
    a = allocate_b0_uniform(t, "e2")
    b = allocate_b0_uniform(t, "e2")
    assert a.to_dict() == b.to_dict()
    assert a.status == "ok"
    assert abs(sum(a.agent_allocations.values()) - 1.0) < 1e-12
    last = allocate_b1_last_touch(t, "e2")
    assert last.status == "ok"
    assert set(last.agent_allocations) == {"A"}  # ancestor excluding outcome prefers e1
    r1 = allocate_rpa(t, "e2", projection_kind=ProjectionKind.P1_DIRECT)
    r2 = allocate_rpa(t, "e2", projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert r1.status == "ok" and r2.status == "ok"
    alias = allocate_b2_p1_equal_share(t, "e2")
    assert alias.agent_allocations == r1.agent_allocations
    assert alias.information_budget == "alias"


def test_markov_documented_not_independent():
    assert MARKOV_STATUS["status"] == "not_implemented_independent"


def test_shapley_exact_small():
    t = _trace()
    s = allocate_b4_shapley(t, "e2", max_exact_agents=12, seed=1)
    assert s.status == "ok"
    assert abs(sum(s.agent_allocations.values()) - 1.0) < 1e-9
    s2 = allocate_b4_shapley(t, "e2", max_exact_agents=12, seed=1)
    assert s.to_dict() == s2.to_dict()


def test_plhc_attacks_detect():
    t = _trace()
    report = evaluate_plhc_attacks(t)
    assert report["clean_control"]["ok"] is True
    for name, row in report["attacks"].items():
        assert row["detected"] is True, name


def test_no_gt_in_baseline_module_source():
    src = Path("agenttrust/evaluation/baselines.py").read_text(encoding="utf-8")
    assert "ground_truth" not in src
    assert "load_ground_truth" not in src
    assert "planted" not in src


def test_edge_prf_and_stats_helpers():
    assert edge_prf({("a", "b")}, {("a", "b")})["f1"] == 1.0
    ci = mean_ci_bootstrap([1.0, 2.0, 3.0], n_boot=200, seed=0)
    assert ci["n"] == 3
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]
    d = paired_mean_diff_ci([1, 2, 3], [0, 1, 2], n_boot=200, seed=0)
    assert abs(d["mean"] - 1.0) < 1e-9
    assert cliffs_delta([3, 4], [1, 2]) > 0
    adj = holm_correct([("a", 0.01), ("b", 0.04)])
    assert adj["a"] <= adj["b"]


def test_disconnected_outcome_ineligible():
    events = [
        make_event("e1", category="reasoning", agent_id="A"),
        make_event("e2", category="decision", event_type="action", agent_id="B"),  # no deps
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    # e1 not an outcome; e2 has only itself as ancestor
    r = allocate_b0_uniform(t, "e2")
    assert r.status == "ok"
    assert "B" in r.agent_allocations
