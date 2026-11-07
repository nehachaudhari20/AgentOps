"""
Assurance dimension evaluators (Phase 2.6.1).

Uses only ProvenanceTrace / RPAResult / MFAVResult.
Must not import or read benchmark ground truth.
"""

from __future__ import annotations

import math
from typing import Optional

from agenttrust.accountability.result import MFAVResult, MFAVStatus
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.assurance.models import CONSERVATION_ABS_TOL, AssuranceStatus
from agenttrust.assurance.result import DimensionResult
from agenttrust.attribution.rpa import RPAResult
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.event import EventRecord

# Normalized MFAV vectors must sum to 1 within this absolute tolerance
NORMALIZED_SUM_TOL = 1e-9

EVENT_REF_KINDS = frozenset({"dependency", "invokes", "retries"})
ARTIFACT_REF_KINDS = frozenset({"input_artifact", "output_artifact"})


def _collect_typed_refs(
    events: tuple[EventRecord, ...],
) -> list[tuple[str, str, str]]:
    """Each ref is (owner_event_id, kind, target_id)."""
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
    return refs


def _resolve_typed(
    kind: str,
    target: str,
    event_ids: set[str],
    artifact_ids: set[str],
) -> str:
    """
    Return resolution class:
      resolved | missing | wrong_namespace
    """
    if kind in EVENT_REF_KINDS:
        if target in event_ids:
            return "resolved"
        if target in artifact_ids:
            return "wrong_namespace"
        return "missing"
    if kind in ARTIFACT_REF_KINDS:
        if target in artifact_ids:
            return "resolved"
        if target in event_ids:
            return "wrong_namespace"
        return "missing"
    return "missing"


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

    if c.has_dependency_cycle:
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.CONTRADICTED,
            value="invalid",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1_1",
            explanation="Dependency cycle detected; trace structure is contradicted for DAG analysis.",
            limitations=limitations,
        )
    if c.incomplete:
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.INCOMPLETE,
            value="incomplete",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1_1",
            explanation="Trace completeness report marks the trace incomplete (unexpected missing parents from the calculator's view).",
            limitations=limitations,
            warnings=["Incomplete traces are not equivalent to complete traces for assurance."],
        )
    if c.suitable_for_dag_attribution:
        return DimensionResult(
            dimension_id="trace_completeness",
            status=AssuranceStatus.VERIFIED,
            value="complete",
            evidence_refs=evidence,
            rule_id="assurance.completeness.v1_1",
            explanation="Trace is complete and suitable for DAG attribution under ProvenanceTrace rules.",
            limitations=limitations,
        )
    return DimensionResult(
        dimension_id="trace_completeness",
        status=AssuranceStatus.UNAVAILABLE,
        value=None,
        evidence_refs=evidence,
        rule_id="assurance.completeness.v1_1",
        explanation="Completeness state is not classifiable as verified/incomplete/invalid.",
        limitations=limitations,
    )


def evaluate_reference_integrity(trace: ProvenanceTrace) -> DimensionResult:
    """
    Typed referential validity (Phase 2.6.1 consolidation).

    Replaces the prior duplicate pair (reference_integrity + provenance_coverage),
    which shared the same untyped numerator/denominator. This single dimension
    reports typed resolution counts and a resolved fraction when n>0.

    Rules:
    - Event-namespace refs (dependency/invokes/retries) resolve only against event IDs.
    - Artifact-namespace refs (input/output) resolve only against artifact IDs.
    - Wrong-namespace hits (e.g. artifact ref → existing event ID) → contradicted.
    - Missing targets → incomplete.
    - Optional metadata (model_id/tool_id) is never required.
    """
    refs = _collect_typed_refs(trace.events)
    event_ids = {e.event_id for e in trace.events}
    artifact_ids = {a.artifact_id for a in trace.artifacts}
    n = len(refs)
    limitations = [
        "Typed namespaces only; union-of-IDs acceptance is rejected.",
        "Does not use ground truth to reclassify planted missing refs.",
        "Optional metadata (model_id/tool_id) is not required evidence.",
        "Phase 2.6.1: provenance_coverage consolidated into this dimension.",
    ]
    if n == 0:
        return DimensionResult(
            dimension_id="reference_integrity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            evidence_refs=[],
            rule_id="assurance.reference_integrity.v1_1",
            explanation="No required lineage references present; measure unavailable (not scored as 1.0).",
            limitations=limitations,
        )

    resolved = 0
    missing: list[dict[str, str]] = []
    wrong_ns: list[dict[str, str]] = []
    for owner, kind, target in refs:
        cls = _resolve_typed(kind, target, event_ids, artifact_ids)
        if cls == "resolved":
            resolved += 1
        elif cls == "wrong_namespace":
            wrong_ns.append({"owner": owner, "ref_type": kind, "target_id": target})
        else:
            missing.append({"owner": owner, "ref_type": kind, "target_id": target})

    fraction = resolved / n
    value = {
        "resolved": resolved,
        "total": n,
        "fraction": fraction,
        "missing": missing[:20],
        "wrong_namespace": wrong_ns[:20],
        "n_missing": len(missing),
        "n_wrong_namespace": len(wrong_ns),
    }
    evidence = [f"n_refs={n}", f"n_resolved={resolved}", f"n_wrong_ns={len(wrong_ns)}"]

    if wrong_ns:
        return DimensionResult(
            dimension_id="reference_integrity",
            status=AssuranceStatus.CONTRADICTED,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.reference_integrity.v1_1",
            explanation=(
                f"{len(wrong_ns)} references resolve in the wrong ID namespace "
                "(event↔artifact cross-hit)."
            ),
            limitations=limitations,
            warnings=[
                f"wrong_ns:{w['owner']}:{w['ref_type']}->{w['target_id']}" for w in wrong_ns[:5]
            ],
        )
    if missing:
        return DimensionResult(
            dimension_id="reference_integrity",
            status=AssuranceStatus.INCOMPLETE,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.reference_integrity.v1_1",
            explanation=f"{len(missing)} required typed references are missing.",
            limitations=limitations,
            warnings=[
                f"missing:{m['owner']}:{m['ref_type']}->{m['target_id']}" for m in missing[:5]
            ],
        )
    return DimensionResult(
        dimension_id="reference_integrity",
        status=AssuranceStatus.VERIFIED,
        value=value,
        evidence_refs=evidence,
        rule_id="assurance.reference_integrity.v1_1",
        explanation="All required typed references resolve in the correct namespace.",
        limitations=limitations,
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
    if has_cycle or (abs_err == abs_err and abs_err > CONSERVATION_ABS_TOL):
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


def _validate_normalized_vector(
    vec: dict[str, float],
    *,
    label: str,
) -> Optional[str]:
    """Return error reason or None if valid against exclusive taxonomy."""
    expected = {f.value for f in FACTOR_ORDER}
    keys = set(vec.keys())
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        return f"{label}: factor support mismatch missing={missing} extra={extra}"
    total = 0.0
    for f in FACTOR_ORDER:
        v = vec[f.value]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return f"{label}: non-numeric value for {f.value}"
        fv = float(v)
        if not math.isfinite(fv):
            return f"{label}: non-finite value for {f.value}"
        if fv < 0.0:
            return f"{label}: negative value for {f.value}"
        total += fv
    if abs(total - 1.0) > NORMALIZED_SUM_TOL:
        return f"{label}: vector sum {total} not within {NORMALIZED_SUM_TOL} of 1"
    return None


def evaluate_attribution_sensitivity(
    mfav_p1: Optional[MFAVResult],
    mfav_p2: Optional[MFAVResult],
) -> DimensionResult:
    limitations = [
        "δ = ½ Σ|M_P1(f)−M_P2(f)| measures descriptive allocation sensitivity only.",
        "δ is not uncertainty, causal disagreement, or fault probability.",
        "Requires P1_DIRECT and P2_ARTIFACT_BRIDGE MFAV results for the same outcome.",
        "Factor keys must match the exclusive taxonomy; missing keys are not zero-filled.",
    ]
    if mfav_p1 is None or mfav_p2 is None:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1_1",
            explanation="Both P1 and P2 MFAV results are required.",
            limitations=limitations,
        )

    # Projection identity
    if mfav_p1.projection_kind != ProjectionKind.P1_DIRECT.value:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1_1",
            explanation=f"mfav_p1.projection_kind={mfav_p1.projection_kind!r} is not P1_DIRECT.",
            limitations=limitations,
        )
    if mfav_p2.projection_kind != ProjectionKind.P2_ARTIFACT_BRIDGE.value:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1_1",
            explanation=f"mfav_p2.projection_kind={mfav_p2.projection_kind!r} is not P2_ARTIFACT_BRIDGE.",
            limitations=limitations,
        )
    if mfav_p1.outcome_id != mfav_p2.outcome_id:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1_1",
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
            rule_id="assurance.attribution_sensitivity.v1_1",
            explanation="One or both MFAV normalized vectors are undefined.",
            limitations=limitations,
        )

    err1 = _validate_normalized_vector(v1, label="P1")
    err2 = _validate_normalized_vector(v2, label="P2")
    if err1 or err2:
        return DimensionResult(
            dimension_id="attribution_sensitivity",
            status=AssuranceStatus.CONTRADICTED,
            value=None,
            rule_id="assurance.attribution_sensitivity.v1_1",
            explanation="; ".join(x for x in (err1, err2) if x),
            limitations=limitations,
        )

    delta = 0.5 * sum(abs(float(v1[f.value]) - float(v2[f.value])) for f in FACTOR_ORDER)
    return DimensionResult(
        dimension_id="attribution_sensitivity",
        status=AssuranceStatus.VERIFIED,
        value={"total_variation": delta, "outcome_id": mfav_p1.outcome_id},
        evidence_refs=[mfav_p1.outcome_id, mfav_p1.projection_kind, mfav_p2.projection_kind],
        rule_id="assurance.attribution_sensitivity.v1_1",
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
