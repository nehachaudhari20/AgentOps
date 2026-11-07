"""
Assurance dimension evaluators.

These functions use only ProvenanceTrace / RPAResult / MFAVResult inputs.
They must not import or read benchmark ground truth.
"""

from __future__ import annotations

from typing import Any, Optional

from agenttrust.accountability.result import MFAVResult, MFAVStatus
from agenttrust.assurance.models import CONSERVATION_ABS_TOL, AssuranceStatus
from agenttrust.assurance.result import DimensionResult
from agenttrust.attribution.rpa import RPAResult
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.event import EventRecord


def _collect_required_refs(
    events: tuple[EventRecord, ...],
) -> tuple[list[tuple[str, str, str]], set[str], set[str]]:
    """
    Return (refs, event_ids, artifact_ids) where each ref is
    (owner_event_id, kind, target_id).
    """
    event_ids = {e.event_id for e in events}
    refs: list[tuple[str, str, str]] = []
    for e in events:
        for d in e.dependency_event_ids:
            refs.append((e.event_id, "dependency", d))
        for d in e.invokes_event_ids:
            refs.append((e.event_id, "invokes", d))
        if e.retries_event_id:
            refs.append((e.event_id, "retries", e.retries_event_id))
        for a in e.input_artifact_ids:
            refs.append((e.event_id, "input_artifact", a))
        for a in e.output_artifact_ids:
            refs.append((e.event_id, "output_artifact", a))
    return refs, event_ids, set()


def evaluate_trace_completeness(trace: ProvenanceTrace) -> DimensionResult:
    c = trace.completeness()
    limitations = [
        "Does not classify intentional vs unexpected incompleteness (requires evaluation-side GT).",
        "Completeness is not a trustworthiness measure.",
    ]
    evidence = [
        f"incomplete={c.incomplete}",
        f"has_dependency_cycle={c.has_dependency_cycle}",
        f"suitable_for_dag_attribution={c.suitable_for_dag_attribution}",
    ]
    if c.missing_dependency_parents:
        evidence.append(f"missing_parents={list(c.missing_dependency_parents)[:8]}")

    if c.has_dependency_cycle or (
        not c.suitable_for_dag_attribution and c.has_dependency_cycle
    ):
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.CONTRADICTED,
            value="invalid",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1",
            explanation="Dependency cycle or invalid DAG suitability for attribution.",
            limitations=limitations,
        )
    if c.incomplete:
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.INCOMPLETE,
            value="incomplete",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1",
            explanation="Trace completeness report marks the trace incomplete.",
            limitations=limitations,
            warnings=["Incomplete traces are not equivalent to complete traces for assurance."],
        )
    if c.suitable_for_dag_attribution:
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.VERIFIED,
            value="complete",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1",
            explanation="Trace is complete and suitable for DAG attribution under ProvenanceTrace rules.",
            limitations=limitations,
        )
    return DimensionResult(
        dimension_id="trace_completeness",
        status=AssuranceStatus.UNAVAILABLE,
        value=None,
        evidence_refs=evidence,
        rule_id="assurance.completeness.v1",
        explanation="Completeness state is not classifiable as verified/incomplete/invalid.",
        limitations=limitations,
    )


def evaluate_reference_integrity(trace: ProvenanceTrace) -> DimensionResult:
    refs, event_ids, _ = _collect_required_refs(trace.events)
    artifact_ids = {a.artifact_id for a in trace.artifacts}
    known = event_ids | artifact_ids
    n = len(refs)
    if n == 0:
        return DimensionResult(
            dimension_id="reference_integrity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            evidence_refs=[],
            rule_id="assurance.reference_integrity.v1",
            explanation="No required lineage references present; measure unavailable.",
            limitations=["Zero required refs → unavailable (not scored as 1.0)."],
        )
    missing: list[str] = []
    ok = 0
    for owner, kind, target in refs:
        if target in known:
            ok += 1
        else:
            missing.append(f"{owner}:{kind}->{target}")
    fraction = ok / n
    value = {"resolved": ok, "total": n, "fraction": fraction, "missing": missing[:20]}
    if ok == n:
        status = AssuranceStatus.VERIFIED
        explanation = "All required references resolve to known events/artifacts."
    else:
        status = AssuranceStatus.INCOMPLETE
        explanation = f"{n - ok} required references do not resolve."
    return DimensionResult(
        dimension_id="reference_integrity",
        status=status,
        value=value,
        evidence_refs=[f"n_refs={n}", f"n_resolved={ok}"],
        rule_id="assurance.reference_integrity.v1",
        explanation=explanation,
        limitations=[
            "Does not use ground truth to reclassify planted missing refs.",
            "Optional metadata (model_id/tool_id) is not required evidence.",
        ],
        warnings=[f"missing_ref:{m}" for m in missing[:5]],
    )


def evaluate_provenance_coverage(trace: ProvenanceTrace) -> DimensionResult:
    refs, event_ids, _ = _collect_required_refs(trace.events)
    artifact_ids = {a.artifact_id for a in trace.artifacts}
    known = event_ids | artifact_ids
    n = len(refs)
    if n == 0:
        return DimensionResult(
            dimension_id="provenance_coverage",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            evidence_refs=[],
            rule_id="assurance.provenance_coverage.v1",
            explanation="Coverage denominator is zero; returning unavailable (no invented value).",
            limitations=["C = n_ok/n only when n>0."],
        )
    ok = sum(1 for _, _, t in refs if t in known)
    c = ok / n
    status = AssuranceStatus.VERIFIED if c == 1.0 else AssuranceStatus.INCOMPLETE
    return DimensionResult(
        dimension_id="provenance_coverage",
        status=status,
        value=c,
        evidence_refs=[f"n_ok={ok}", f"n={n}"],
        rule_id="assurance.provenance_coverage.v1",
        explanation=f"Provenance coverage C={c}.",
        limitations=["Coverage is reference resolution, not causal completeness."],
    )


def evaluate_attribution_computability(rpa: Optional[RPAResult]) -> DimensionResult:
    if rpa is None:
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_computability.v1",
            explanation="No RPAResult provided.",
            limitations=["Conserved allocation is not causal responsibility."],
        )
    cons = rpa.conservation or {}
    abs_err = float(cons.get("abs_error_from_one_nodes", float("nan")))
    has_cycle = bool((rpa.cycle_diagnostics or {}).get("has_cycle"))
    value = {
        "projection_kind": rpa.projection_kind,
        "alpha": rpa.alpha,
        "conservation": dict(cons),
        "has_cycle": has_cycle,
        "overridden_guards": list(rpa.overridden_guards),
        "warnings": list(rpa.warnings),
    }
    evidence = [rpa.outcome_id, rpa.projection_kind, rpa.algorithm_version]
    if has_cycle or (
        abs_err == abs_err and abs_err > CONSERVATION_ABS_TOL  # not NaN and too large
    ):
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.CONTRADICTED,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.attribution_computability.v1",
            explanation="RPA result shows cycle and/or conservation failure beyond tolerance.",
            limitations=["Conserved allocation is not causal responsibility."],
            warnings=list(rpa.warnings),
        )
    if rpa.overridden_guards or bool((rpa.completeness or {}).get("incomplete")):
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.INCOMPLETE,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.attribution_computability.v1",
            explanation="RPA ran under incomplete/overridden conditions.",
            limitations=["Conserved allocation is not causal responsibility."],
            warnings=list(rpa.warnings) + list(rpa.overridden_guards),
        )
    return DimensionResult(
        dimension_id="attribution_computability",
        status=AssuranceStatus.VERIFIED,
        value=value,
        evidence_refs=evidence,
        rule_id="assurance.attribution_computability.v1",
        explanation="RPA result is conserved within tolerance without cycle flags.",
        limitations=["Conserved allocation is not causal responsibility."],
        warnings=list(rpa.warnings),
    )


def evaluate_attribution_sensitivity(
    mfav_p1: Optional[MFAVResult],
    mfav_p2: Optional[MFAVResult],
) -> DimensionResult:
    limitations = [
        "δ is descriptive P1/P2 difference, not uncertainty or agent fault.",
        "Requires defined normalized MFAV vectors for the same outcome.",
    ]
    if mfav_p1 is None or mfav_p2 is None:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1",
            explanation="Both P1 and P2 MFAV results are required.",
            limitations=limitations,
        )
    if mfav_p1.outcome_id != mfav_p2.outcome_id:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1",
            explanation="P1/P2 MFAV outcome_ids differ; not comparable.",
            limitations=limitations,
        )
    v1 = mfav_p1.normalized_factor_vector
    v2 = mfav_p2.normalized_factor_vector
    if v1 is None or v2 is None:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1",
            explanation="One or both MFAV normalized vectors are undefined.",
            limitations=limitations,
        )
    delta = 0.5 * sum(abs(v1.get(f.value, 0.0) - v2.get(f.value, 0.0)) for f in FACTOR_ORDER)
    return DimensionResult(
        dimension_id="attribution_sensitivity",
        status=AssuranceStatus.VERIFIED,
        value={"total_variation": delta, "outcome_id": mfav_p1.outcome_id},
        evidence_refs=[mfav_p1.outcome_id, mfav_p1.projection_kind, mfav_p2.projection_kind],
        rule_id="assurance.attribution_sensitivity.v1",
        explanation=f"P1/P2 MFAV total variation δ={delta}.",
        limitations=limitations,
    )


def evaluate_factor_profile(mfav: Optional[MFAVResult]) -> DimensionResult:
    limitations = [
        "Factor allocation is descriptive structural distribution, not a trust score.",
        "Factor concentration/entropy are not computed as assurance metrics.",
    ]
    if mfav is None:
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.factor_profile.v1",
            explanation="No MFAVResult provided.",
            limitations=limitations,
        )
    value = {
        "raw_factor_allocations": dict(mfav.raw_factor_allocations),
        "normalized_factor_vector": (
            None if mfav.normalized_factor_vector is None else dict(mfav.normalized_factor_vector)
        ),
        "total_raw_allocation": mfav.total_raw_allocation,
        "conservation_error": mfav.conservation_error,
        "mfav_status": mfav.status.value,
        "complete": mfav.complete,
    }
    if mfav.status == MFAVStatus.COMPLETE and mfav.normalized_factor_vector is not None:
        status = AssuranceStatus.VERIFIED
        explanation = "MFAV factor profile is complete with a defined normalized vector."
    elif mfav.status in (MFAVStatus.ZERO_ALLOCATION, MFAVStatus.UNDEFINED):
        status = AssuranceStatus.UNAVAILABLE
        explanation = f"MFAV status {mfav.status.value}; factor vector not defined."
    else:
        status = AssuranceStatus.INCOMPLETE
        explanation = f"MFAV status {mfav.status.value}; profile incomplete or overridden."
    return DimensionResult(
        dimension_id="factor_profile",
        status=status,
        value=value,
        evidence_refs=[mfav.outcome_id, mfav.projection_kind, mfav.mfav_algorithm_version],
        rule_id="assurance.factor_profile.v1",
        explanation=explanation,
        limitations=limitations,
        warnings=list(mfav.classification_warnings)[:5],
    )
