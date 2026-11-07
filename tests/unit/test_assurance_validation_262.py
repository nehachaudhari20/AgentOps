"""Phase 2.6.2 adversarial regression: fail-closed RPA + MFAV factor validation."""

from __future__ import annotations

import copy
import json
import math
import pytest

from agenttrust import (
    AssuranceProfileCalculator,
    AssuranceStatus,
    ConservedRPA,
    MFAV,
    ProvenanceTrace,
)
from agenttrust.accountability.result import EventAssignment, MFAVResult, MFAVStatus
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.assurance.dimensions import (
    evaluate_attribution_computability,
    evaluate_factor_profile,
)
from agenttrust.assurance.models import ASSURANCE_ALGORITHM_VERSION, worst_status
from agenttrust.attribution.rpa import RPAResult
from agenttrust.mlpg.projections import ProjectionKind
from tests.conftest import make_artifact, make_event


def _uniform() -> dict[str, float]:
    n = len(FACTOR_ORDER)
    return {f.value: 1.0 / n for f in FACTOR_ORDER}


def _agent_mass_vector(mass: float = 1.0) -> dict[str, float]:
    raw = {f.value: 0.0 for f in FACTOR_ORDER}
    raw["agent"] = mass
    return raw


def _assignment(
    event_id: str,
    factor: str,
    allocation: float,
) -> EventAssignment:
    return EventAssignment(
        event_id=event_id,
        factor=factor,
        allocation=allocation,
        entity_id="E",
        entity_kind="agent",
        unidentified=False,
    )


def _valid_rpa(**overrides) -> RPAResult:
    nodes = {"e1": 0.4, "e2": 0.6}
    s = sum(nodes.values())
    base = dict(
        outcome_id="e2",
        projection_kind=ProjectionKind.P1_DIRECT.value,
        algorithm_name="conserved_rpa",
        algorithm_version="test",
        alpha=0.0,
        parent_allocation_policy="uniform",
        node_allocations=dict(nodes),
        root_allocations={"e1": 1.0},
        conservation={
            "sum_node_allocations": s,
            "sum_root_allocations": 1.0,
            "abs_error_from_one_nodes": abs(s - 1.0),
            "abs_error_from_one_roots": 0.0,
        },
        completeness={"incomplete": False},
        cycle_diagnostics={"has_cycle": False},
        config={},
        reproducibility={},
        warnings=[],
        overridden_guards=[],
    )
    base.update(overrides)
    return RPAResult(**base)


def _valid_mfav(**overrides) -> MFAVResult:
    """COMPLETE MFAV with consistent event assignment ↔ raw factor mass on agent."""
    vec = _agent_mass_vector(1.0)
    base = dict(
        outcome_id="out",
        projection_kind=ProjectionKind.P1_DIRECT.value,
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
        event_assignments=[_assignment("e1", "agent", 1.0)],
        secondary_subtype_totals={},
        unidentified_contributions=[],
    )
    base.update(overrides)
    return MFAVResult(**base)


def _complete_trace():
    events = [
        make_event("e1", category="reasoning", agent_id="A", outputs=["a1"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"], inputs=["a1"]),
    ]
    arts = [make_artifact("a1", "x")]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    return t


# --- RPA adversarial ---


def test_rpa_valid_conserved_verified():
    dim = evaluate_attribution_computability(_valid_rpa())
    assert dim.status == AssuranceStatus.VERIFIED
    assert dim.rule_id == "assurance.attribution_computability.v1_2"


def test_rpa_missing_result_unavailable():
    assert evaluate_attribution_computability(None).status == AssuranceStatus.UNAVAILABLE


def test_rpa_missing_conservation_dict():
    rpa = _valid_rpa(conservation=None)  # type: ignore[arg-type]
    dim = evaluate_attribution_computability(rpa)
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert "conservation" in dim.explanation.lower()


def test_rpa_empty_conservation_dict():
    dim = evaluate_attribution_computability(_valid_rpa(conservation={}))
    assert dim.status == AssuranceStatus.UNAVAILABLE


@pytest.mark.parametrize("missing_key", ["abs_error_from_one_nodes", "sum_node_allocations"])
def test_rpa_missing_conservation_field(missing_key):
    cons = {
        "sum_node_allocations": 1.0,
        "abs_error_from_one_nodes": 0.0,
    }
    del cons[missing_key]
    dim = evaluate_attribution_computability(_valid_rpa(conservation=cons))
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert missing_key in dim.explanation


@pytest.mark.parametrize(
    "bad_err",
    [float("nan"), float("inf"), float("-inf")],
)
def test_rpa_nonfinite_conservation_error(bad_err):
    cons = {
        "sum_node_allocations": 1.0,
        "abs_error_from_one_nodes": bad_err,
    }
    dim = evaluate_attribution_computability(_valid_rpa(conservation=cons))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "non-finite" in dim.explanation


@pytest.mark.parametrize(
    "bad_val",
    [float("nan"), float("inf"), float("-inf"), -0.5],
)
def test_rpa_bad_node_allocation(bad_val):
    nodes = {"e1": 0.5, "e2": bad_val}
    # Keep reported conservation consistent with a fake sum so node check fires first
    # when bad_val is negative/nan/inf; for nan/inf the node check is enough.
    dim = evaluate_attribution_computability(
        _valid_rpa(
            node_allocations=nodes,
            conservation={
                "sum_node_allocations": 1.0,
                "abs_error_from_one_nodes": 0.0,
            },
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_rpa_empty_node_allocations():
    dim = evaluate_attribution_computability(
        _valid_rpa(
            node_allocations={},
            conservation={"sum_node_allocations": 0.0, "abs_error_from_one_nodes": 1.0},
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "empty" in dim.explanation.lower()


def test_rpa_reported_sum_inconsistent():
    dim = evaluate_attribution_computability(
        _valid_rpa(
            conservation={
                "sum_node_allocations": 0.5,  # actual S=1.0
                "abs_error_from_one_nodes": 0.0,
            }
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "sum_node_allocations" in dim.explanation


def test_rpa_reported_error_inconsistent():
    dim = evaluate_attribution_computability(
        _valid_rpa(
            conservation={
                "sum_node_allocations": 1.0,
                "abs_error_from_one_nodes": 0.5,  # actual |S-1|=0
            }
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "abs_error_from_one_nodes" in dim.explanation


@pytest.mark.parametrize("alpha", [float("nan"), float("inf"), -0.1, 1.1])
def test_rpa_bad_alpha(alpha):
    dim = evaluate_attribution_computability(_valid_rpa(alpha=alpha))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "alpha" in dim.explanation.lower()


def test_rpa_cycle_flag_contradicted():
    dim = evaluate_attribution_computability(
        _valid_rpa(cycle_diagnostics={"has_cycle": True})
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "cycle" in dim.explanation.lower()


def test_rpa_incomplete_never_verified():
    dim = evaluate_attribution_computability(
        _valid_rpa(
            completeness={"incomplete": True},
            overridden_guards=["allow_incomplete"],
        )
    )
    assert dim.status == AssuranceStatus.INCOMPLETE


def test_rpa_nan_error_does_not_fail_open_to_verified():
    """Regression: NaN abs_err must not fall through to verified."""
    cons = {
        "sum_node_allocations": 1.0,
        "abs_error_from_one_nodes": float("nan"),
    }
    dim = evaluate_attribution_computability(_valid_rpa(conservation=cons))
    assert dim.status != AssuranceStatus.VERIFIED
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_pipeline_rpa_still_verified():
    t = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(t)[0]
    dim = evaluate_attribution_computability(rpa)
    assert dim.status == AssuranceStatus.VERIFIED


# --- MFAV adversarial ---


def test_mfav_valid_complete_verified():
    dim = evaluate_factor_profile(_valid_mfav())
    assert dim.status == AssuranceStatus.VERIFIED
    assert dim.rule_id == "assurance.factor_profile.v1_2"


def test_mfav_missing_factor_key():
    vec = _uniform()
    del vec["other"]
    # renormalize remaining so sum isn't the first failure
    s = sum(vec.values())
    vec = {k: v / s for k, v in vec.items()}
    dim = evaluate_factor_profile(
        _valid_mfav(
            raw_factor_allocations=dict(vec),
            normalized_factor_vector=dict(vec),
            total_raw_allocation=1.0,
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "support" in dim.explanation.lower() or "missing" in dim.explanation.lower()


def test_mfav_extra_factor_key():
    vec = _uniform()
    vec["ghost"] = 0.0
    dim = evaluate_factor_profile(
        _valid_mfav(raw_factor_allocations=dict(vec), normalized_factor_vector=dict(vec))
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.2])
def test_mfav_bad_normalized_value(bad):
    vec = _agent_mass_vector(1.0)
    vec["agent"] = bad
    dim = evaluate_factor_profile(_valid_mfav(normalized_factor_vector=dict(vec)))
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_non_normalized_vector():
    vec = _agent_mass_vector(1.0)
    vec["agent"] = 1.5
    dim = evaluate_factor_profile(_valid_mfav(normalized_factor_vector=dict(vec)))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "sum" in dim.explanation


def test_mfav_missing_normalized_vector():
    dim = evaluate_factor_profile(_valid_mfav(normalized_factor_vector=None))
    assert dim.status == AssuranceStatus.UNAVAILABLE


@pytest.mark.parametrize("bad", [float("nan"), -0.3])
def test_mfav_bad_raw_allocation(bad):
    raw = _uniform()
    raw["tool"] = bad
    dim = evaluate_factor_profile(
        _valid_mfav(raw_factor_allocations=raw, total_raw_allocation=sum(
            v for v in raw.values() if isinstance(v, float) and math.isfinite(v)
        ))
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_inconsistent_total_raw():
    dim = evaluate_factor_profile(_valid_mfav(total_raw_allocation=0.5))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "total_raw" in dim.explanation


def test_mfav_missing_conservation_error_nan():
    # dataclass requires conservation_error; NaN means invalid present value
    dim = evaluate_factor_profile(_valid_mfav(conservation_error=float("nan")))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "conservation_error" in dim.explanation


def test_mfav_invalid_large_conservation_error():
    dim = evaluate_factor_profile(_valid_mfav(conservation_error=0.5))
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_incomplete_never_verified():
    dim = evaluate_factor_profile(
        _valid_mfav(status=MFAVStatus.INCOMPLETE, complete=False)
    )
    assert dim.status == AssuranceStatus.INCOMPLETE


def test_mfav_overridden_never_verified():
    dim = evaluate_factor_profile(
        _valid_mfav(status=MFAVStatus.OVERRIDDEN, complete=False)
    )
    assert dim.status == AssuranceStatus.INCOMPLETE


def test_mfav_complete_status_alone_insufficient():
    """COMPLETE status with malformed vector must not verify."""
    vec = _agent_mass_vector(1.0)
    vec["agent"] = float("nan")
    dim = evaluate_factor_profile(
        _valid_mfav(status=MFAVStatus.COMPLETE, complete=True, normalized_factor_vector=vec)
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


# --- Phase 2.6.2.1 event-assignment conservation ---


def test_mfav_missing_event_assignments():
    dim = evaluate_factor_profile(_valid_mfav(event_assignments=None))  # type: ignore[arg-type]
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert "event_assignments" in dim.explanation.lower()


def test_mfav_empty_assignments_with_positive_raw():
    dim = evaluate_factor_profile(_valid_mfav(event_assignments=[]))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "empty" in dim.explanation.lower()


def test_mfav_duplicate_event_ids():
    dim = evaluate_factor_profile(
        _valid_mfav(
            event_assignments=[
                _assignment("e1", "agent", 0.5),
                _assignment("e1", "agent", 0.5),
            ]
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "duplicate" in dim.explanation.lower()


def test_mfav_unknown_factor_label_in_assignment():
    dim = evaluate_factor_profile(
        _valid_mfav(event_assignments=[_assignment("e1", "not_a_factor", 1.0)])
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "taxonomy" in dim.explanation.lower() or "factor" in dim.explanation.lower()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -0.4])
def test_mfav_bad_event_allocation(bad):
    dim = evaluate_factor_profile(
        _valid_mfav(event_assignments=[_assignment("e1", "agent", bad)])
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_event_sum_differs_from_raw_total():
    dim = evaluate_factor_profile(
        _valid_mfav(event_assignments=[_assignment("e1", "agent", 0.5)])
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "T_events" in dim.explanation or "disagrees" in dim.explanation


def test_mfav_event_factor_totals_differ_from_raw_map():
    """Mass moved between factors in assignments while totals still match."""
    raw = _agent_mass_vector(1.0)
    # assignments put mass on tool; raw still says agent
    dim = evaluate_factor_profile(
        _valid_mfav(
            raw_factor_allocations=raw,
            normalized_factor_vector=raw,
            event_assignments=[_assignment("e1", "tool", 1.0)],
            total_raw_allocation=1.0,
            conservation_error=0.0,
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "tool" in dim.explanation or "agent" in dim.explanation


def test_mfav_one_factor_inconsistent_while_totals_match():
    """Swap mass between two factors in raw vs assignments with equal totals."""
    raw = {f.value: 0.0 for f in FACTOR_ORDER}
    raw["agent"] = 0.6
    raw["tool"] = 0.4
    # assignments reverse the split
    dim = evaluate_factor_profile(
        _valid_mfav(
            raw_factor_allocations=raw,
            normalized_factor_vector=raw,
            total_raw_allocation=1.0,
            conservation_error=0.0,
            event_assignments=[
                _assignment("e1", "agent", 0.4),
                _assignment("e2", "tool", 0.6),
            ],
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_reported_conservation_error_disagrees():
    dim = evaluate_factor_profile(_valid_mfav(conservation_error=1e-3))
    assert dim.status == AssuranceStatus.CONTRADICTED
    assert "conservation_error" in dim.explanation


def test_mfav_tampered_assignments_unchanged_raw():
    dim = evaluate_factor_profile(
        _valid_mfav(
            event_assignments=[
                _assignment("e1", "agent", 0.7),
                _assignment("e2", "model", 0.3),
            ]
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_tampered_raw_unchanged_assignments():
    raw = _agent_mass_vector(1.0)
    raw["agent"] = 0.5
    raw["model"] = 0.5
    dim = evaluate_factor_profile(
        _valid_mfav(
            raw_factor_allocations=raw,
            normalized_factor_vector=raw,
            total_raw_allocation=1.0,
            event_assignments=[_assignment("e1", "agent", 1.0)],
            conservation_error=0.0,
        )
    )
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_mfav_zero_allocation_remains_unavailable():
    zero = {f.value: 0.0 for f in FACTOR_ORDER}
    dim = evaluate_factor_profile(
        _valid_mfav(
            status=MFAVStatus.ZERO_ALLOCATION,
            complete=False,
            raw_factor_allocations=zero,
            normalized_factor_vector=None,
            total_raw_allocation=0.0,
            conservation_error=0.0,
            event_assignments=[],
        )
    )
    assert dim.status == AssuranceStatus.UNAVAILABLE


def test_mfav_undefined_remains_unavailable():
    dim = evaluate_factor_profile(
        _valid_mfav(
            status=MFAVStatus.UNDEFINED,
            complete=False,
            normalized_factor_vector=None,
        )
    )
    assert dim.status == AssuranceStatus.UNAVAILABLE


def test_pipeline_mfav_still_verified():
    t = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(t)[0]
    mfav = MFAV().compute(rpa, trace=t)
    dim = evaluate_factor_profile(mfav)
    assert dim.status == AssuranceStatus.VERIFIED


# --- Profile consistency ---


def test_overall_worst_status_precedence():
    statuses = [
        AssuranceStatus.VERIFIED,
        AssuranceStatus.UNAVAILABLE,
        AssuranceStatus.INCOMPLETE,
        AssuranceStatus.CONTRADICTED,
    ]
    assert worst_status(statuses) == AssuranceStatus.CONTRADICTED


def test_malformed_rpa_blocks_overall_verified():
    t = _complete_trace()
    bad = _valid_rpa(
        conservation={
            "sum_node_allocations": 1.0,
            "abs_error_from_one_nodes": float("nan"),
        }
    )
    profile = AssuranceProfileCalculator().compute(t, rpa_result=bad)
    assert profile.dimensions["attribution_computability"].status == AssuranceStatus.CONTRADICTED
    assert profile.overall_status == AssuranceStatus.CONTRADICTED


def test_malformed_mfav_blocks_overall_verified():
    t = _complete_trace()
    rpa = ConservedRPA().allocate_from_trace(t)[0]
    bad = _valid_mfav(normalized_factor_vector=None)
    profile = AssuranceProfileCalculator().compute(t, rpa_result=rpa, mfav_result=bad)
    assert profile.dimensions["factor_profile"].status == AssuranceStatus.UNAVAILABLE
    # overall may be unavailable (not verified) because factor_profile unavailable
    # and sensitivity unavailable — wait: other dims may be verified; overall = worst
    # verified < unavailable in precedence? unavailable is worse than verified
    assert profile.overall_status != AssuranceStatus.VERIFIED


def test_no_fabricated_zero_for_missing_conservation():
    dim = evaluate_attribution_computability(_valid_rpa(conservation={}))
    assert dim.status == AssuranceStatus.UNAVAILABLE
    assert dim.value is not None  # structured value still present
    # Must not claim verified with invented zero error


def test_algorithm_version_2621():
    assert ASSURANCE_ALGORITHM_VERSION == "2.6.2.1"
    t = _complete_trace()
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.algorithm_version == "2.6.2.1"
    blob = json.dumps(profile.to_dict())
    assert '"value": null' in blob or profile.dimensions["attribution_computability"].value is None


def test_inputs_not_mutated_with_adversarial_objects():
    t = _complete_trace()
    rpa = _valid_rpa()
    mfav = _valid_mfav()
    rpa_before = copy.deepcopy(rpa.to_dict())
    mfav_before = copy.deepcopy(mfav.to_dict())
    fp = t.fingerprint()
    AssuranceProfileCalculator().compute(t, rpa_result=rpa, mfav_result=mfav)
    assert rpa.to_dict() == rpa_before
    assert mfav.to_dict() == mfav_before
    assert t.fingerprint() == fp
