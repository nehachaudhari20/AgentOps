"""Phase 2.6 Assurance Profile unit tests."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from agenttrust import (
    AssuranceProfileCalculator,
    AssuranceStatus,
    ConservedRPA,
    MFAV,
    ProvenanceTrace,
)
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


def test_complete_trace_verified_dimensions():
    trace = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)[0]
    mfav = MFAV().compute(rpa, trace=trace)
    profile = AssuranceProfileCalculator().compute(trace, rpa_result=rpa, mfav_result=mfav)
    assert profile.dimensions["trace_completeness"].status == AssuranceStatus.VERIFIED
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.VERIFIED
    assert profile.dimensions["provenance_coverage"].value == 1.0
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
    assert profile.dimensions["provenance_coverage"].status == AssuranceStatus.INCOMPLETE
    assert profile.dimensions["provenance_coverage"].value < 1.0


def test_unexpected_missing_reference():
    events = [make_event("e1", category="tool", event_type="tool_call", inputs=["ghost-art"])]
    t = ProvenanceTrace()
    t.load_records(events, [])
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.INCOMPLETE
    missing = profile.dimensions["reference_integrity"].value["missing"]
    assert any("ghost-art" in m for m in missing)


def test_zero_denominator_coverage_unavailable():
    # Event with no deps/artifacts → no required refs
    events = [make_event("solo", category="other", deps=[], inputs=[], outputs=[])]
    t = ProvenanceTrace()
    t.load_records(events, [])
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["provenance_coverage"].status == AssuranceStatus.UNAVAILABLE
    assert profile.dimensions["provenance_coverage"].value is None
    assert profile.dimensions["reference_integrity"].status == AssuranceStatus.UNAVAILABLE


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


def test_p1_p2_sensitivity_and_unavailable():
    arts = [make_artifact("ax", "bridge")]
    events = [
        make_event("e1", category="reasoning", outputs=["ax"]),
        make_event("e2", category="decision", event_type="action", inputs=["ax"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    engine = ConservedRPA()
    r1 = engine.allocate(t.project(ProjectionKind.P1_DIRECT), "e2", completeness=t.completeness())
    r2 = engine.allocate(t.project(ProjectionKind.P2_ARTIFACT_BRIDGE), "e2", completeness=t.completeness())
    m1 = MFAV().compute(r1, trace=t)
    m2 = MFAV().compute(r2, trace=t)
    profile = AssuranceProfileCalculator().compute(
        t, rpa_result=r1, mfav_result=m1, mfav_p1=m1, mfav_p2=m2
    )
    assert profile.dimensions["attribution_sensitivity"].status == AssuranceStatus.VERIFIED
    assert "total_variation" in profile.dimensions["attribution_sensitivity"].value

    alone = AssuranceProfileCalculator().compute(t, mfav_p1=m1)
    assert alone.dimensions["attribution_sensitivity"].status == AssuranceStatus.UNAVAILABLE


def test_mfav_integration_and_no_trust_score():
    trace = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(trace)[0]
    mfav = MFAV().compute(rpa, trace=trace)
    profile = AssuranceProfileCalculator().compute(trace, rpa_result=rpa, mfav_result=mfav)
    d = profile.to_dict()
    blob = str(d).lower()
    assert "trust_score" not in blob
    assert "probability" not in blob or "not" in profile.disclaimer.lower()
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
    import inspect

    for mod in (calc_mod, dim_mod):
        src = inspect.getsource(mod)
        assert "ground_truth" not in src
        assert "BenchmarkGroundTruth" not in src


def test_generator_version_mismatch_exits():
    path = Path(__file__).resolve().parents[2] / "experiments" / "scripts" / "validate_phase25_fault_matrix.py"
    spec = importlib.util.spec_from_file_location("vfm", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(SystemExit) as ei:
        mod.require_matching_generator_version("0.0.0", expected="2.5.1")
    assert ei.value.code == 2
