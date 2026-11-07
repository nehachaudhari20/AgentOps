"""Phase 2.6.1 Assurance Profile unit tests."""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import math
from pathlib import Path

import pytest

from agenttrust import (
    AssuranceProfileCalculator,
    AssuranceStatus,
    ConservedRPA,
    MFAV,
    ProvenanceTrace,
)
from agenttrust.accountability.result import MFAVResult, MFAVStatus
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.assurance.dimensions import (
    NORMALIZED_SUM_TOL,
    evaluate_attribution_sensitivity,
    evaluate_reference_integrity,
)
from agenttrust.assurance.models import ASSURANCE_ALGORITHM_VERSION
from agenttrust.attribution.rpa import RPAConfig, RPAError
from agenttrust.mlpg.projections import ProjectionKind
from tests.conftest import make_artifact, make_event


def _complete_trace():
    events = [
        make_event("e1", category="reasoning", agent_id="A", outputs=["a1"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"], inputs=["a1"]),
    ]
    arts = [make_artifact("a1", "x")]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    return t


def _uniform_vector() -> dict[str, float]:
    n = len(FACTOR_ORDER)
    return {f.value: 1.0 / n for f in FACTOR_ORDER}


def _fake_mfav(
    *,
    outcome_id: str = "out",
    projection_kind: str = ProjectionKind.P1_DIRECT.value,
    vector: dict[str, float] | None = None,
) -> MFAVResult:
    vec = vector if vector is not None else _uniform_vector()
    return MFAVResult(
        outcome_id=outcome_id,
        projection_kind=projection_kind,
        rpa_algorithm_name="test",
        rpa_algorithm_version="0",
        rpa_alpha=0.0,
        parent_allocation_policy="test",
        mfav_algorithm_name="test",
        mfav_algorithm_version="0",
        taxonomy_version="2.3.0",
        mapping_policy="test",
        raw_factor_allocations=dict(vec),
        normalized_factor_vector=dict(vec),
        total_raw_allocation=1.0,
        conservation_error=0.0,
        status=MFAVStatus.COMPLETE,
        complete=True,
        entity_contributions=[],
        event_assignments=[],
        secondary_subtype_totals={},
        unidentified_contributions=[],
    )


def test_complete_trace_verified_dimensions():
    trace = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)[0]
    mfav = MFAV().compute(rpa, trace=trace)
    profile = AssuranceProfileCalculator().compute(trace, rpa_result=rpa, mfav_result=mfav)
    assert ASSURANCE_ALGORITHM_VERSION == "2.6.2.1"
    assert "provenance_coverage" not in profile.dimensions
    assert set(profile.dimensions) == {
        "trace_completeness",
        "reference_integrity",
        "attribution_computability",
        "attribution_sensitivity",
        "factor_profile",
    }
    assert profile.dimensions["trace_completeness"].status == AssuranceStatus.VERIFIED
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.VERIFIED
    assert profile.dimensions["reference_integrity"].value["fraction"] == 1.0
    assert profile.dimensions["attribution_computability"].status == AssuranceStatus.VERIFIED
    assert profile.dimensions["factor_profile"].status == AssuranceStatus.VERIFIED


def test_incomplete_trace_status():
    events = [
        make_event("e1", category="reasoning", deps=["missing-parent"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    assert t.completeness().incomplete
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["trace_completeness"].status == AssuranceStatus.INCOMPLETE
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.INCOMPLETE
    assert profile.dimensions["reference_integrity"].value["fraction"] < 1.0
    assert profile.overall_status != AssuranceStatus.VERIFIED


def test_dependency_cycle_contradicted():
    events = [
        make_event("e1", category="reasoning", deps=["e2"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    assert t.completeness().has_dependency_cycle
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["trace_completeness"].status == AssuranceStatus.CONTRADICTED
    assert profile.overall_status == AssuranceStatus.CONTRADICTED


def test_artifact_ref_to_event_id_wrong_namespace():
    """Artifact reference points to an existing event ID → contradicted."""
    events = [
        make_event("e1", category="reasoning"),
        make_event("e2", category="decision", event_type="action", inputs=["e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    dim = evaluate_reference_integrity(t)
    assert dim.status == AssuranceStatus.CONTRADICTED
    wrong = dim.value["wrong_namespace"]
    assert any(
        w["owner"] == "e2" and w["ref_type"] == "input_artifact" and w["target_id"] == "e1"
        for w in wrong
    )
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.overall_status != AssuranceStatus.VERIFIED


def test_event_ref_to_artifact_id_wrong_namespace():
    """Event reference points to an existing artifact ID → contradicted."""
    arts = [make_artifact("a1", "x")]
    events = [make_event("e1", category="reasoning", deps=["a1"], outputs=["a1"])]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    dim = evaluate_reference_integrity(t)
    assert dim.status == AssuranceStatus.CONTRADICTED
    wrong = dim.value["wrong_namespace"]
    assert any(
        w["owner"] == "e1" and w["ref_type"] == "dependency" and w["target_id"] == "a1"
        for w in wrong
    )


def test_valid_event_and_artifact_refs():
    t = _complete_trace()
    dim = evaluate_reference_integrity(t)
    assert dim.status == AssuranceStatus.VERIFIED
    assert dim.value["n_wrong_namespace"] == 0
    assert dim.value["n_missing"] == 0
    assert dim.value["fraction"] == 1.0


def test_unexpected_missing_reference_reports_owner_type_target():
    events = [make_event("e1", category="tool", event_type="tool_call", inputs=["ghost-art"])]
    t = ProvenanceTrace()
    t.load_records(events, [])
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.INCOMPLETE
    missing = profile.dimensions["reference_integrity"].value["missing"]
    assert any(
        m["owner"] == "e1" and m["ref_type"] == "input_artifact" and m["target_id"] == "ghost-art"
        for m in missing
    )


def test_duplicate_typed_refs_schema_collapses():
    """Schema deduplicates dependency_event_ids; integrity sees post-schema tuples."""
    events = [
        make_event("e1", category="reasoning"),
        make_event("e2", category="decision", event_type="action", deps=["e1", "e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    assert t.events[1].dependency_event_ids == ("e1",)
    dim = evaluate_reference_integrity(t)
    assert dim.value["total"] == 1
    assert dim.value["resolved"] == 1
    assert dim.status == AssuranceStatus.VERIFIED


def test_zero_denominator_reference_integrity_unavailable():
    events = [make_event("solo", category="other", deps=[], inputs=[], outputs=[])]
    t = ProvenanceTrace()
    t.load_records(events, [])
    profile = AssuranceProfileCalculator().compute(t)
    assert "provenance_coverage" not in profile.dimensions
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.UNAVAILABLE
    assert profile.dimensions["reference_integrity"].value is None


def test_empty_dimensions_produce_unavailable():
    t = _complete_trace()
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["attribution_computability"].status == AssuranceStatus.UNAVAILABLE
    assert profile.dimensions["attribution_sensitivity"].status == AssuranceStatus.UNAVAILABLE
    assert profile.dimensions["factor_profile"].status == AssuranceStatus.UNAVAILABLE


def test_serialization_preserves_null_for_unavailable():
    t = _complete_trace()
    profile = AssuranceProfileCalculator().compute(t)
    blob = json.dumps(profile.to_dict())
    parsed = json.loads(blob)
    assert parsed["dimensions"]["attribution_computability"]["value"] is None
    assert '"value": null' in blob


def test_overall_never_verified_when_required_dim_blocking():
    # Wrong-namespace → contradicted overall
    events = [
        make_event("e1", category="reasoning"),
        make_event("e2", category="tool", event_type="tool_call", inputs=["e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    rpa = None
    try:
        rpa = ConservedRPA().allocate_from_trace(
            t, projection_kind=ProjectionKind.P1_DIRECT, config=RPAConfig(allow_incomplete=True)
        )[0]
    except RPAError:
        pass
    profile = AssuranceProfileCalculator().compute(t, rpa_result=rpa)
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.CONTRADICTED
    assert profile.overall_status == AssuranceStatus.CONTRADICTED


def test_rpa_missing_unavailable():
    trace = _complete_trace()
    profile = AssuranceProfileCalculator().compute(trace, rpa_result=None)
    assert profile.dimensions["attribution_computability"].status == AssuranceStatus.UNAVAILABLE


def test_rpa_incomplete_override():
    events = [
        make_event("e1", category="reasoning", deps=["missing"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, [])
    with pytest.raises(RPAError):
        ConservedRPA().allocate_from_trace(t, projection_kind=ProjectionKind.P1_DIRECT)
    rpa = ConservedRPA().allocate_from_trace(
        t, projection_kind=ProjectionKind.P1_DIRECT, config=RPAConfig(allow_incomplete=True)
    )[0]
    profile = AssuranceProfileCalculator().compute(t, rpa_result=rpa)
    assert profile.dimensions["attribution_computability"].status == AssuranceStatus.INCOMPLETE
    assert profile.overall_status != AssuranceStatus.VERIFIED


def test_p1_p2_sensitivity_valid():
    arts = [make_artifact("ax", "bridge")]
    events = [
        make_event("e1", category="reasoning", outputs=["ax"]),
        make_event("e2", category="decision", event_type="action", inputs=["ax"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    engine = ConservedRPA()
    r1 = engine.allocate(t.project(ProjectionKind.P1_DIRECT), "e2", completeness=t.completeness())
    r2 = engine.allocate(
        t.project(ProjectionKind.P2_ARTIFACT_BRIDGE), "e2", completeness=t.completeness()
    )
    m1 = MFAV().compute(r1, trace=t)
    m2 = MFAV().compute(r2, trace=t)
    profile = AssuranceProfileCalculator().compute(
        t, rpa_result=r1, mfav_result=m1, mfav_p1=m1, mfav_p2=m2
    )
    assert profile.dimensions["attribution_sensitivity"].status == AssuranceStatus.VERIFIED
    assert "total_variation" in profile.dimensions["attribution_sensitivity"].value
    alone = AssuranceProfileCalculator().compute(t, mfav_p1=m1)
    assert alone.dimensions["attribution_sensitivity"].status == AssuranceStatus.UNAVAILABLE


def test_sensitivity_labels_reversed():
    p1 = _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value)
    p2 = _fake_mfav(projection_kind=ProjectionKind.P1_DIRECT.value)
    dim = evaluate_attribution_sensitivity(p1, p2)
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert "P1_DIRECT" in dim.explanation


def test_sensitivity_same_projection_twice():
    p1 = _fake_mfav(projection_kind=ProjectionKind.P1_DIRECT.value)
    p2 = _fake_mfav(projection_kind=ProjectionKind.P1_DIRECT.value)
    dim = evaluate_attribution_sensitivity(p1, p2)
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert "P2_ARTIFACT_BRIDGE" in dim.explanation


def test_sensitivity_different_outcomes():
    p1 = _fake_mfav(outcome_id="a")
    p2 = _fake_mfav(
        outcome_id="b", projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value
    )
    dim = evaluate_attribution_sensitivity(p1, p2)
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert "outcome" in dim.explanation.lower()


def test_sensitivity_nan_and_inf():
    bad_nan = _uniform_vector()
    bad_nan["agent"] = float("nan")
    dim = evaluate_attribution_sensitivity(
        _fake_mfav(vector=bad_nan),
        _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value),
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "non-finite" in dim.explanation

    bad_inf = _uniform_vector()
    bad_inf["agent"] = float("inf")
    dim2 = evaluate_attribution_sensitivity(
        _fake_mfav(vector=bad_inf),
        _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value),
    )
    assert dim2.status == AssuranceStatus.CONTRADICTED


def test_sensitivity_negative_and_non_normalized():
    neg = _uniform_vector()
    neg["agent"] = -0.1
    neg["other"] = neg["other"] + 0.1
    dim = evaluate_attribution_sensitivity(
        _fake_mfav(vector=neg),
        _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value),
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "negative" in dim.explanation

    unnorm = _uniform_vector()
    unnorm["agent"] = unnorm["agent"] + 0.5
    dim2 = evaluate_attribution_sensitivity(
        _fake_mfav(vector=unnorm),
        _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value),
    )
    assert dim2.status == AssuranceStatus.CONTRADICTED
    assert "sum" in dim2.explanation


def test_sensitivity_missing_factor_keys():
    incomplete = {f.value: 0.0 for f in FACTOR_ORDER if f.value != "other"}
    # renormalize remaining so sum issue isn't the first failure
    n = len(incomplete)
    for k in incomplete:
        incomplete[k] = 1.0 / n
    dim = evaluate_attribution_sensitivity(
        _fake_mfav(vector=incomplete),
        _fake_mfav(projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value),
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "factor support" in dim.explanation


def test_sensitivity_valid_comparable_vectors():
    v1 = _uniform_vector()
    v2 = {f.value: 0.0 for f in FACTOR_ORDER}
    v2["agent"] = 1.0
    dim = evaluate_attribution_sensitivity(
        _fake_mfav(vector=v1),
        _fake_mfav(
            projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE.value, vector=v2
        ),
    )
    assert dim.status == AssuranceStatus.VERIFIED
    expected = 0.5 * sum(abs(v1[f.value] - v2[f.value]) for f in FACTOR_ORDER)
    assert math.isclose(dim.value["total_variation"], expected, abs_tol=NORMALIZED_SUM_TOL)
    assert "descriptive" in " ".join(dim.limitations).lower()


def test_mfav_integration_and_no_trust_score():
    trace = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(trace)[0]
    mfav = MFAV().compute(rpa, trace=trace)
    profile = AssuranceProfileCalculator().compute(trace, rpa_result=rpa, mfav_result=mfav)
    d = profile.to_dict()
    blob = str(d).lower()
    assert "trust_score" not in blob
    assert "other" in profile.dimensions["factor_profile"].value["raw_factor_allocations"]


def test_deterministic_and_no_mutation():
    trace = _complete_trace()
    fp = trace.fingerprint()
    rpa = ConservedRPA().allocate_from_trace(trace)[0]
    before = copy.deepcopy(rpa.to_dict())
    mfav = MFAV().compute(rpa, trace=trace)
    mb = copy.deepcopy(mfav.to_dict())
    calc = AssuranceProfileCalculator()
    a = calc.compute(trace, rpa_result=rpa, mfav_result=mfav)
    b = calc.compute(trace, rpa_result=rpa, mfav_result=mfav)
    assert a.to_dict() == b.to_dict()
    assert rpa.to_dict() == before
    assert mfav.to_dict() == mb
    assert trace.fingerprint() == fp


def test_calculator_does_not_import_ground_truth():
    import agenttrust.assurance.calculator as calc_mod
    import agenttrust.assurance.dimensions as dim_mod

    for mod in (calc_mod, dim_mod):
        src = inspect.getsource(mod)
        assert "ground_truth" not in src
        assert "BenchmarkGroundTruth" not in src


def test_optional_metadata_absence_not_incomplete():
    """Missing model_id/tool_id must not make reference integrity incomplete."""
    events = [
        make_event("e1", category="reasoning", agent_id="A", model_id=None, outputs=["a1"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"], inputs=["a1"]),
    ]
    # Explicitly omit model_id/tool_id
    for e in events:
        e.pop("model_id", None)
        e.pop("tool_id", None)
    arts = [make_artifact("a1", "x")]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    dim = evaluate_reference_integrity(t)
    assert dim.status == AssuranceStatus.VERIFIED


def test_evaluate_script_fail_closed_on_errors(tmp_path, monkeypatch):
    path = (
        Path(__file__).resolve().parents[2]
        / "experiments"
        / "scripts"
        / "evaluate_assurance_profiles.py"
    )
    spec = importlib.util.spec_from_file_location("eval_ap", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Point corpora at empty / missing dirs under tmp
    missing = tmp_path / "no_such_corpus"
    empty = tmp_path / "empty_corpus"
    empty.mkdir()
    out = tmp_path / "out"
    out.mkdir()

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    # Rewrite main paths by calling _evaluate_dir directly
    r1 = mod._evaluate_dir(missing, None, "missing")
    r2 = mod._evaluate_dir(empty, None, "empty")
    assert r1["n_errors"] >= 1
    assert r2["n_errors"] >= 1
    assert any(e.get("error") for e in r1["invalid_or_error"])


def test_generator_version_mismatch_exits():
    path = (
        Path(__file__).resolve().parents[2]
        / "experiments"
        / "scripts"
        / "validate_phase25_fault_matrix.py"
    )
    spec = importlib.util.spec_from_file_location("vfm", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(SystemExit) as ei:
        mod.require_matching_generator_version("0.0.0", expected="2.5.1")
    assert ei.value.code == 2
