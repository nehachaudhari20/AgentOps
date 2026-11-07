"""Phase 2.8 end-to-end pipeline unit and adversarial tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agenttrust.accountability.result import MFAVResult, MFAVStatus
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.assurance.models import AssuranceStatus
from agenttrust.attribution.rpa import RPAResult
from agenttrust.integrity.result import IntegrityStatus
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.pipeline import AgentTrustPipeline, PipelineConfig, load_trace_inputs
from agenttrust.pipeline.io import PipelineIOError, assert_no_ground_truth_path
from agenttrust.pipeline.validation import validate_mfav_result, validate_rpa_result
from tests.conftest import make_artifact, make_event


def _complete_records():
    events = [
        make_event("e1", category="reasoning", agent_id="A", outputs=["a1"]),
        make_event(
            "e2",
            category="decision",
            event_type="action",
            deps=["e1"],
            inputs=["a1"],
            agent_id="B",
        ),
    ]
    arts = [make_artifact("a1", "payload")]
    return events, arts


def _write_trace(tmp: Path, events, arts, name: str = "t1") -> Path:
    d = tmp / name
    d.mkdir(parents=True)
    (d / "events.json").write_text(
        json.dumps({"events": events}, indent=2) + "\n", encoding="utf-8"
    )
    (d / "artifacts.json").write_text(
        json.dumps({"artifacts": arts}, indent=2) + "\n", encoding="utf-8"
    )
    return d


# --- Happy path ---


def test_complete_valid_trace_pipeline():
    events, arts = _complete_records()
    res = AgentTrustPipeline().run_records(events, arts, trace_id="complete")
    assert res.ok is True
    assert res.hard_error is None
    assert res.plhc["status"] == "ok"
    assert res.plhc["verification"]["status"] == IntegrityStatus.VERIFIED.value
    assert res.rpa["status"] == "ok"
    assert res.mfav["status"] == "ok"
    assert res.assurance["status"] == "ok"
    assert len(res.assurance["profiles"]) >= 1
    dims = res.assurance["profiles"][0]["dimensions"]
    assert "provenance_coverage" not in dims
    assert dims["audit_integrity"]["status"] == AssuranceStatus.VERIFIED.value
    kinds = {r["projection_kind"] for r in res.rpa["results"]}
    assert ProjectionKind.P1_DIRECT.value in kinds
    assert ProjectionKind.P2_ARTIFACT_BRIDGE.value in kinds


def test_determinism_repeated_runs():
    events, arts = _complete_records()
    pipe = AgentTrustPipeline(PipelineConfig())
    a = pipe.run_records(events, arts, trace_id="det").deterministic_payload()
    b = pipe.run_records(events, arts, trace_id="det").deterministic_payload()
    assert a == b


def test_p1_p2_both_run_independently():
    # Artifact-mediated lineage without DEPENDS_ON so P2 adds a bridge edge P1 lacks
    events = [
        make_event("e1", category="reasoning", agent_id="A", outputs=["a1"]),
        make_event(
            "e2",
            category="decision",
            event_type="action",
            inputs=["a1"],
            agent_id="B",
        ),
    ]
    arts = [make_artifact("a1", "payload")]
    res = AgentTrustPipeline().run_records(events, arts, trace_id="both")
    p1 = [r for r in res.rpa["results"] if r["projection_kind"] == "P1_DIRECT"]
    p2 = [r for r in res.rpa["results"] if r["projection_kind"] == "P2_ARTIFACT_BRIDGE"]
    assert p1 and p2
    assert p1[0]["status"] == "ok" and p2[0]["status"] == "ok"
    assert res.projection_eligibility["P1_DIRECT"]["n_edges"] == 0
    assert res.projection_eligibility["P2_ARTIFACT_BRIDGE"]["n_artifact_bridge_edges"] >= 1
    assert (
        res.projection_eligibility["P2_ARTIFACT_BRIDGE"]["n_edges"]
        > res.projection_eligibility["P1_DIRECT"]["n_edges"]
    )


def test_no_p2_config():
    events, arts = _complete_records()
    res = AgentTrustPipeline(PipelineConfig(run_p2=False)).run_records(
        events, arts, trace_id="nop2"
    )
    assert "P2_ARTIFACT_BRIDGE" not in res.projection_eligibility
    assert all(r["projection_kind"] == "P1_DIRECT" for r in res.rpa["results"])


# --- Schema / reference / dependency failures ---


def test_invalid_event_schema():
    events = [{"event_id": "bad", "not_a_real_field": True}]
    res = AgentTrustPipeline().run_records(events, [], trace_id="bad-schema")
    # Rejected events → may have no outcomes
    assert res.validation.get("counts", {}).get("rejected_events", 0) >= 1 or not res.ok
    assert res.provenance_fingerprint is not None or res.hard_error


def test_invalid_artifact_reference():
    events = [
        make_event("e1", category="decision", event_type="action", inputs=["missing-art"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="bad-ref")
    assert res.graph_summary["completeness"]["incomplete"] is True
    # Without allow_incomplete, RPA ineligible; PLHC/assurance still run
    assert res.rpa["status"] in ("ineligible", "failed", "partial")


def test_missing_dependency():
    events = [
        make_event("e2", category="decision", event_type="action", deps=["e-missing"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="missing-dep")
    assert res.graph_summary["completeness"]["incomplete"] is True
    assert "e-missing" in res.graph_summary["completeness"]["missing_dependency_parents"]


def test_cyclic_dependency():
    events = [
        make_event("e1", category="reasoning", deps=["e2"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="cycle")
    assert res.graph_summary["completeness"]["has_dependency_cycle"] is True
    assert res.rpa["status"] in ("ineligible", "failed")


def test_incomplete_trace_distinguishable():
    events = [
        make_event("e1", category="decision", event_type="action", deps=["ghost"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="inc")
    assert res.graph_summary["completeness"]["incomplete"] is True
    assert any("incomplete" in w.lower() for w in res.warnings)
    # Not silently treated as complete success for attribution
    assert res.rpa["status"] != "ok" or res.config["allow_incomplete_rpa"]


def test_allow_incomplete_override():
    events = [
        make_event("e1", category="decision", event_type="action", deps=["ghost"]),
    ]
    res = AgentTrustPipeline(PipelineConfig(allow_incomplete_rpa=True)).run_records(
        events, [], trace_id="inc-allow"
    )
    # May succeed RPA with overridden guards
    if res.rpa["status"] == "ok":
        assert any(r.get("validation", {}).get("status") == "incomplete" for r in res.rpa["results"])


# --- Multiple outcomes ---


def test_multiple_outcomes():
    events = [
        make_event("e0", category="reasoning"),
        make_event("e1", category="decision", event_type="action", deps=["e0"]),
        make_event("e2", category="decision", event_type="action", deps=["e0"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="multi")
    p1 = [r for r in res.rpa["results"] if r["projection_kind"] == "P1_DIRECT"]
    assert len(p1) >= 2
    assert {r["outcome_id"] for r in p1} >= {"e1", "e2"}


# --- MFAV / RPA validation ---


def test_mfav_aggregation_and_conservation():
    events, arts = _complete_records()
    res = AgentTrustPipeline().run_records(events, arts, trace_id="mfav")
    for entry in res.mfav["results"]:
        assert entry["status"] == "ok"
        assert entry["validation"]["status"] == "verified"
        vec = entry["result"]["normalized_factor_vector"]
        assert abs(sum(vec.values()) - 1.0) < 1e-9


def test_invalid_rpa_result_detected():
    bad = RPAResult(
        outcome_id="o",
        projection_kind="P1_DIRECT",
        algorithm_name="x",
        algorithm_version="0",
        alpha=0.0,
        parent_allocation_policy="equal_parents",
        node_allocations={"a": 0.5},
        root_allocations={"a": 0.5},
        conservation={
            "sum_node_allocations": 0.5,
            "sum_root_allocations": 0.5,
            "abs_error_from_one_nodes": 0.5,
            "abs_error_from_one_roots": 0.5,
        },
        completeness={},
        cycle_diagnostics={"has_cycle": False},
        config={},
        reproducibility={},
    )
    v = validate_rpa_result(bad)
    assert v["valid"] is False
    assert v["status"] == "contradicted"


def test_invalid_mfav_result_detected():
    vec = {f.value: 0.0 for f in FACTOR_ORDER}
    vec[FACTOR_ORDER[0].value] = 1.0
    bad = MFAVResult(
        outcome_id="o",
        projection_kind="P1_DIRECT",
        rpa_algorithm_name="x",
        rpa_algorithm_version="0",
        rpa_alpha=0.0,
        parent_allocation_policy="equal_parents",
        mfav_algorithm_name="x",
        mfav_algorithm_version="0",
        taxonomy_version="2.3.0",
        mapping_policy="x",
        raw_factor_allocations=dict(vec),
        normalized_factor_vector=dict(vec),
        total_raw_allocation=1.0,
        conservation_error=0.5,  # disagrees with recomputed 0
        status=MFAVStatus.COMPLETE,
        complete=True,
        entity_contributions=[],
        event_assignments=[],
        secondary_subtype_totals={},
        unidentified_contributions=[],
    )
    v = validate_mfav_result(bad)
    assert v["status"] in ("contradicted", "unavailable")


# --- PLHC failure ---


def test_plhc_tampered_checkpoint_fails():
    events, arts = _complete_records()
    pipe = AgentTrustPipeline()
    real_create = pipe._plhc.create_checkpoint

    def _tampered(snapshot, **kwargs):
        cp = real_create(snapshot, **kwargs)
        from agenttrust.integrity.checkpoint import IntegrityCheckpoint

        return IntegrityCheckpoint(
            sequence_number=cp.sequence_number,
            previous_checkpoint_hash=cp.previous_checkpoint_hash,
            merkle_root="0" * 64,
            leaf_count=cp.leaf_count,
            canonicalization_version=cp.canonicalization_version,
            hash_algorithm=cp.hash_algorithm,
            checkpoint_format_version=cp.checkpoint_format_version,
            merkle_format_version=cp.merkle_format_version,
            created_at=cp.created_at,
            checkpoint_hash=cp.checkpoint_hash,
        )

    with patch.object(pipe._plhc, "create_checkpoint", side_effect=_tampered):
        res = pipe.run_records(events, arts, trace_id="tamper")
    assert res.plhc["status"] == "failed"
    assert res.ok is False


# --- Assurance statuses ---


def test_unavailable_and_not_applicable_dimensions():
    # No RPA (no outcomes): attribution dims unavailable
    events = [make_event("e1", category="reasoning")]  # not a decision/action outcome
    res = AgentTrustPipeline().run_records(events, [], trace_id="no-out")
    assert res.rpa["status"] == "ineligible"
    assert res.assurance["status"] == "ok"
    dims = res.assurance["profiles"][0]["dimensions"]
    assert dims["attribution_computability"]["status"] == AssuranceStatus.UNAVAILABLE.value
    assert dims["factor_profile"]["status"] == AssuranceStatus.UNAVAILABLE.value
    # sensitivity without pair
    assert dims["attribution_sensitivity"]["status"] in (
        AssuranceStatus.UNAVAILABLE.value,
        AssuranceStatus.NOT_APPLICABLE.value,
    )


# --- Ground-truth leakage ---


def test_refuse_ground_truth_path(tmp_path: Path):
    gt = tmp_path / "ground_truth" / "x.json"
    gt.parent.mkdir()
    gt.write_text("{}", encoding="utf-8")
    with pytest.raises(PipelineIOError):
        assert_no_ground_truth_path(gt)
    with pytest.raises(PipelineIOError):
        assert_no_ground_truth_path(tmp_path / "ground_truth")


def test_pipeline_does_not_read_ground_truth(tmp_path: Path):
    events, arts = _complete_records()
    tdir = _write_trace(tmp_path, events, arts, "bench-x")
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    gt_file = gt_dir / "bench-x.json"
    gt_file.write_text(
        json.dumps({"planted_responsibility": {"e1": 1.0}, "fault_labels": ["x"]}),
        encoding="utf-8",
    )

    opened: list[str] = []
    real_open = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        opened.append(str(self))
        return real_open(self, *args, **kwargs)

    with patch.object(Path, "read_text", tracking_read_text):
        # Also track read_bytes used by load_trace_inputs
        real_rb = Path.read_bytes

        def tracking_rb(self, *args, **kwargs):
            opened.append(str(self))
            return real_rb(self, *args, **kwargs)

        with patch.object(Path, "read_bytes", tracking_rb):
            res = AgentTrustPipeline().run_trace_dir(tdir)

    assert res.ok is True
    assert not any("ground_truth" in p.replace("\\", "/") for p in opened)
    assert any("events.json" in p for p in opened)
    assert any("artifacts.json" in p for p in opened)


def test_load_trace_inputs_only_events_artifacts(tmp_path: Path):
    events, arts = _complete_records()
    tdir = _write_trace(tmp_path, events, arts)
    (tdir / "ground_truth.json").write_text("{}", encoding="utf-8")
    ev, ar, fp = load_trace_inputs(tdir)
    assert len(ev) == 2 and len(ar) == 1 and len(fp) == 64


# --- Failure propagation ---


def test_pipeline_failure_propagation_io(tmp_path: Path):
    missing = tmp_path / "nope"
    res = AgentTrustPipeline().run_trace_dir(missing)
    assert res.ok is False
    assert res.hard_error is not None


def test_corpus_does_not_conceal_failures(tmp_path: Path):
    good_e, good_a = _complete_records()
    _write_trace(tmp_path, good_e, good_a, "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "events.json").write_text("{not-json", encoding="utf-8")
    (bad / "artifacts.json").write_text(
        json.dumps({"artifacts": []}), encoding="utf-8"
    )
    summary, results = AgentTrustPipeline().run_corpus(tmp_path, corpus_label="t")
    assert summary.n_examined == 2
    assert summary.n_failed >= 1
    assert summary.n_success >= 1
    assert any(not r.ok for r in results)


def test_timing_excluded_from_deterministic_payload():
    events, arts = _complete_records()
    res = AgentTrustPipeline().run_records(events, arts, trace_id="t")
    assert res.timing_ms is not None
    assert "timing_ms" not in res.deterministic_payload()


def test_p1_p2_eligibility_difference_no_silent_substitute():
    # Events with only DEPENDS_ON, no artifact bridge — both still eligible but P2 bridges=0
    events = [
        make_event("e1", category="reasoning"),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    res = AgentTrustPipeline().run_records(events, [], trace_id="dep-only")
    assert res.projection_eligibility["P1_DIRECT"]["eligible"] is True
    assert res.projection_eligibility["P2_ARTIFACT_BRIDGE"]["eligible"] is True
    assert res.projection_eligibility["P2_ARTIFACT_BRIDGE"]["n_artifact_bridge_edges"] == 0
    # Results labeled with their own projection kinds
    for r in res.rpa["results"]:
        assert r["result"]["projection_kind"] == r["projection_kind"]
