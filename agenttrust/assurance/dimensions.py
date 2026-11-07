"""
Assurance dimension evaluators (Phase 2.7).

Uses ProvenanceTrace / RPAResult / MFAVResult / optional PLHC result.
Must not import or read benchmark ground truth.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from agenttrust.accountability.result import MFAVResult, MFAVStatus
from agenttrust.accountability.taxonomy import FACTOR_ORDER
from agenttrust.assurance.models import (
    ALLOCATION_NONNEG_TOL,
    CONSERVATION_ABS_TOL,
    REPORT_AGREEMENT_TOL,
    AssuranceStatus,
)
from agenttrust.assurance.result import DimensionResult
from agenttrust.attribution.rpa import RPAResult
from agenttrust.integrity.result import IntegrityStatus, IntegrityVerificationResult
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.event import EventRecord

# Normalized MFAV vectors must sum to 1 within this absolute tolerance
NORMALIZED_SUM_TOL = 1e-9

EVENT_REF_KINDS = frozenset({"dependency", "invokes", "retries"})
ARTIFACT_REF_KINDS = frozenset({"input_artifact", "output_artifact"})

_REQUIRED_CONSERVATION_KEYS = ("abs_error_from_one_nodes", "sum_node_allocations")


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


def _is_real_number(v: Any) -> bool:
    """True iff v is an int/float suitable for numeric validation (not bool)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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


def _validate_rpa_conservation_evidence(rpa: RPAResult) -> tuple[Optional[str], Optional[str]]:
    """
    Fail-closed RPA conservation validation (Phase 2.6.2).

    Returns (kind, reason) where kind is:
      None — valid conservation evidence
      "unavailable" — required evidence missing (not treated as zero)
      "contradicted" — malformed / inconsistent / non-conserved / cycle / bad alpha
    """
    limitations_note = ""  # unused; kept for clarity of return contract

    # --- Alpha ---
    if not _is_real_number(rpa.alpha):
        return "contradicted", f"alpha is non-numeric: {rpa.alpha!r}"
    alpha = float(rpa.alpha)
    if not math.isfinite(alpha):
        return "contradicted", f"alpha is non-finite: {alpha}"
    if not (0.0 <= alpha <= 1.0):
        return "contradicted", f"alpha={alpha} outside [0, 1]"

    # --- Conservation dict presence ---
    cons = rpa.conservation
    if cons is None or not isinstance(cons, dict):
        return "unavailable", "conservation dictionary missing"
    if not cons:
        return "unavailable", "conservation dictionary empty"

    missing_keys = [k for k in _REQUIRED_CONSERVATION_KEYS if k not in cons]
    if missing_keys:
        return "unavailable", f"missing required conservation fields: {missing_keys}"

    # --- Required conservation field values ---
    for key in _REQUIRED_CONSERVATION_KEYS:
        raw = cons[key]
        if not _is_real_number(raw):
            return "contradicted", f"conservation.{key} is non-numeric: {raw!r}"
        fv = float(raw)
        if not math.isfinite(fv):
            return "contradicted", f"conservation.{key} is non-finite: {fv}"
        if fv < -ALLOCATION_NONNEG_TOL:
            return "contradicted", f"conservation.{key} is negative: {fv}"

    reported_sum = float(cons["sum_node_allocations"])
    reported_abs_err = float(cons["abs_error_from_one_nodes"])

    # --- Node allocations ---
    nodes = rpa.node_allocations
    if nodes is None or not isinstance(nodes, dict):
        return "contradicted", "node_allocations missing or not a mapping"
    if len(nodes) == 0:
        return "contradicted", "node_allocations is empty; not a valid conserved result"

    s = 0.0
    for nid, aval in nodes.items():
        if not _is_real_number(aval):
            return "contradicted", f"node_allocations[{nid!r}] is non-numeric: {aval!r}"
        fv = float(aval)
        if not math.isfinite(fv):
            return "contradicted", f"node_allocations[{nid!r}] is non-finite: {fv}"
        if fv < -ALLOCATION_NONNEG_TOL:
            return "contradicted", f"node_allocations[{nid!r}] is negative: {fv}"
        s += fv

    eps_computed = abs(s - 1.0)

    if abs(reported_sum - s) > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"reported sum_node_allocations={reported_sum} disagrees with "
            f"recomputed S={s} (tol={REPORT_AGREEMENT_TOL})",
        )
    if abs(reported_abs_err - eps_computed) > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"reported abs_error_from_one_nodes={reported_abs_err} disagrees with "
            f"recomputed |S-1|={eps_computed} (tol={REPORT_AGREEMENT_TOL})",
        )
    if eps_computed > CONSERVATION_ABS_TOL:
        return (
            "contradicted",
            f"allocations not conserved: |S-1|={eps_computed} > {CONSERVATION_ABS_TOL}",
        )

    # --- Cycle diagnostics ---
    cycle = rpa.cycle_diagnostics or {}
    if bool(cycle.get("has_cycle")):
        return "contradicted", "cycle_diagnostics.has_cycle is true"

    _ = limitations_note
    return None, None


def evaluate_attribution_computability(rpa: Optional[RPAResult]) -> DimensionResult:
    """
    Fail-closed attribution computability (rule assurance.attribution_computability.v1_2).

    Missing conservation evidence → unavailable (never treated as zero).
    Malformed / inconsistent / non-conserved / cycle / bad alpha → contradicted.
    Valid under incomplete/overridden guards → incomplete (never verified).
    Valid conserved finite consistent result → verified.
    """
    limitations = [
        "Conserved allocation is not causal responsibility.",
        f"Conservation abs tol={CONSERVATION_ABS_TOL}; report agreement tol={REPORT_AGREEMENT_TOL}.",
        f"Non-negativity float allowance={ALLOCATION_NONNEG_TOL}.",
        "Missing conservation metrics are not substituted with zero.",
    ]
    if rpa is None:
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.attribution_computability.v1_2",
            explanation="No RPAResult provided.",
            limitations=limitations,
        )

    cons = rpa.conservation if isinstance(rpa.conservation, dict) else {}
    has_cycle = bool((rpa.cycle_diagnostics or {}).get("has_cycle"))
    value = {
        "projection_kind": rpa.projection_kind,
        "alpha": rpa.alpha,
        "conservation": dict(cons) if isinstance(cons, dict) else cons,
        "has_cycle": has_cycle,
        "overridden_guards": list(rpa.overridden_guards),
        "warnings": list(rpa.warnings),
        "n_node_allocations": (
            len(rpa.node_allocations) if isinstance(rpa.node_allocations, dict) else None
        ),
    }
    evidence = [rpa.outcome_id, rpa.projection_kind, rpa.algorithm_version]

    kind, reason = _validate_rpa_conservation_evidence(rpa)
    if kind == "unavailable":
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.UNAVAILABLE,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.attribution_computability.v1_2",
            explanation=reason or "Required RPA conservation evidence unavailable.",
            limitations=limitations,
            warnings=list(rpa.warnings),
        )
    if kind == "contradicted":
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.CONTRADICTED,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.attribution_computability.v1_2",
            explanation=reason or "RPA conservation evidence contradicted.",
            limitations=limitations,
            warnings=list(rpa.warnings),
        )

    if rpa.overridden_guards or bool((rpa.completeness or {}).get("incomplete")):
        return DimensionResult(
            dimension_id="attribution_computability",
            status=AssuranceStatus.INCOMPLETE,
            value=value,
            evidence_refs=evidence,
            rule_id="assurance.attribution_computability.v1_2",
            explanation="RPA ran under incomplete/overridden conditions.",
            limitations=limitations,
            warnings=list(rpa.warnings) + list(rpa.overridden_guards),
        )
    return DimensionResult(
        dimension_id="attribution_computability",
        status=AssuranceStatus.VERIFIED,
        value=value,
        evidence_refs=evidence,
        rule_id="assurance.attribution_computability.v1_2",
        explanation="RPA result is conserved, internally consistent, and free of cycle flags.",
        limitations=limitations,
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
        if not _is_real_number(v):
            return f"{label}: non-numeric value for {f.value}"
        fv = float(v)
        if not math.isfinite(fv):
            return f"{label}: non-finite value for {f.value}"
        if fv < -ALLOCATION_NONNEG_TOL:
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


def _validate_mfav_factor_profile(mfav: MFAVResult) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (kind, reason): None/None if structurally valid for COMPLETE verification path;
    "unavailable" or "contradicted" otherwise.

    Phase 2.6.2.1: independently verifies event_assignments ↔ raw factors ↔
    reported totals ↔ conservation_error. Does not trust MFAVStatus.COMPLETE alone.
    Missing evidence is never replaced with zero.
    """
    if not isinstance(mfav.outcome_id, str) or not mfav.outcome_id:
        return "contradicted", "outcome_id missing or invalid"
    if not isinstance(mfav.projection_kind, str) or not mfav.projection_kind:
        return "contradicted", "projection_kind missing or invalid"

    raw = mfav.raw_factor_allocations
    if raw is None or not isinstance(raw, dict):
        return "unavailable", "raw_factor_allocations missing"

    expected = {f.value for f in FACTOR_ORDER}
    raw_keys = set(raw.keys())
    if raw_keys != expected:
        return (
            "contradicted",
            f"raw factor support mismatch missing={sorted(expected - raw_keys)} "
            f"extra={sorted(raw_keys - expected)}",
        )

    t_factors = 0.0
    for f in FACTOR_ORDER:
        v = raw[f.value]
        if not _is_real_number(v):
            return "contradicted", f"raw[{f.value}] non-numeric: {v!r}"
        fv = float(v)
        if not math.isfinite(fv):
            return "contradicted", f"raw[{f.value}] non-finite: {fv}"
        if fv < -ALLOCATION_NONNEG_TOL:
            return "contradicted", f"raw[{f.value}] negative: {fv}"
        t_factors += fv

    if not _is_real_number(mfav.total_raw_allocation):
        return "contradicted", f"total_raw_allocation non-numeric: {mfav.total_raw_allocation!r}"
    t_reported = float(mfav.total_raw_allocation)
    if not math.isfinite(t_reported):
        return "contradicted", f"total_raw_allocation non-finite: {t_reported}"
    if t_reported < -ALLOCATION_NONNEG_TOL:
        return "contradicted", f"total_raw_allocation negative: {t_reported}"
    if abs(t_reported - t_factors) > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"total_raw_allocation={t_reported} disagrees with sum(raw)={t_factors}",
        )

    # --- Event assignments (Phase 2.6.2.1) ---
    assignments = mfav.event_assignments
    if assignments is None:
        return "unavailable", "event_assignments missing"
    if not isinstance(assignments, list):
        return "contradicted", "event_assignments is not a list"

    if len(assignments) == 0 and t_factors > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"event_assignments empty but T_factors={t_factors} > 0",
        )
    if len(assignments) == 0 and abs(t_factors) <= REPORT_AGREEMENT_TOL:
        # Zero mass with no assignments: only admissible when status is ZERO/UNDEFINED
        # (handled before this validator). Treat as missing assignment evidence.
        return "unavailable", "event_assignments empty with zero factor mass"

    seen_ids: set[str] = set()
    t_events = 0.0
    by_factor = {f.value: 0.0 for f in FACTOR_ORDER}

    for i, a in enumerate(assignments):
        eid = getattr(a, "event_id", None)
        factor = getattr(a, "factor", None)
        alloc = getattr(a, "allocation", None)
        if not isinstance(eid, str) or not eid:
            return "contradicted", f"event_assignments[{i}].event_id missing or empty"
        if eid in seen_ids:
            return "contradicted", f"duplicate event_id in event_assignments: {eid!r}"
        seen_ids.add(eid)
        if not isinstance(factor, str) or factor not in expected:
            return (
                "contradicted",
                f"event_assignments[{i}] factor {factor!r} not in exclusive taxonomy",
            )
        if not _is_real_number(alloc):
            return "contradicted", f"event_assignments[{i}].allocation non-numeric: {alloc!r}"
        av = float(alloc)
        if not math.isfinite(av):
            return "contradicted", f"event_assignments[{i}].allocation non-finite: {av}"
        if av < -ALLOCATION_NONNEG_TOL:
            return "contradicted", f"event_assignments[{i}].allocation negative: {av}"
        t_events += av
        by_factor[factor] += av

    if abs(t_events - t_factors) > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"T_events={t_events} disagrees with T_factors={t_factors}",
        )

    for f in FACTOR_ORDER:
        fv = float(raw[f.value])
        if abs(by_factor[f.value] - fv) > REPORT_AGREEMENT_TOL:
            return (
                "contradicted",
                f"factor {f.value}: assignment sum={by_factor[f.value]} "
                f"disagrees with raw={fv}",
            )

    if not _is_real_number(mfav.conservation_error):
        return "unavailable", "conservation_error missing or non-numeric"
    cerr = float(mfav.conservation_error)
    if not math.isfinite(cerr):
        return "contradicted", f"conservation_error non-finite: {cerr}"
    if cerr < -ALLOCATION_NONNEG_TOL:
        return "contradicted", f"conservation_error negative: {cerr}"

    # Reconstructed MFAV conservation: |T_factors − T_events|
    # (equals |factor_total − incoming_total| when each RPA node becomes one assignment).
    eps_mfav = abs(t_factors - t_events)
    if abs(cerr - eps_mfav) > REPORT_AGREEMENT_TOL:
        return (
            "contradicted",
            f"reported conservation_error={cerr} disagrees with "
            f"recomputed |T_factors-T_events|={eps_mfav}",
        )

    norm = mfav.normalized_factor_vector
    if norm is None:
        return "unavailable", "normalized_factor_vector missing"

    nerr = _validate_normalized_vector(norm, label="normalized")
    if nerr:
        return "contradicted", nerr

    if mfav.status == MFAVStatus.COMPLETE and eps_mfav > CONSERVATION_ABS_TOL:
        return (
            "contradicted",
            f"ε_MFAV={eps_mfav} exceeds tol={CONSERVATION_ABS_TOL} for COMPLETE MFAV",
        )
    if mfav.status == MFAVStatus.COMPLETE and cerr > CONSERVATION_ABS_TOL:
        return (
            "contradicted",
            f"conservation_error={cerr} exceeds tol={CONSERVATION_ABS_TOL} for COMPLETE MFAV",
        )

    return None, None


def evaluate_factor_profile(mfav: Optional[MFAVResult]) -> DimensionResult:
    """
    Factor-profile validation (rule assurance.factor_profile.v1_2).

    Does not trust MFAVStatus alone. Does not zero-fill missing factors.
    Independently checks event_assignments ↔ raw factors ↔ conservation_error.
    """
    limitations = [
        "Factor allocation is descriptive structural distribution, not a trust score.",
        "Factor concentration/entropy are not computed as assurance metrics.",
        "Missing factors are not silently inserted as zeros during validation.",
        "ε_MFAV = |T_factors − T_events| from event_assignments and raw factor map.",
        f"Normalized sum tol={NORMALIZED_SUM_TOL}; agreement tol={REPORT_AGREEMENT_TOL}.",
    ]
    rule_id = "assurance.factor_profile.v1_2"
    if mfav is None:
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id=rule_id,
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
        "n_event_assignments": (
            len(mfav.event_assignments) if isinstance(mfav.event_assignments, list) else None
        ),
    }
    evidence = [mfav.outcome_id, mfav.projection_kind, mfav.mfav_algorithm_version]

    if mfav.status in (MFAVStatus.ZERO_ALLOCATION, MFAVStatus.UNDEFINED):
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.UNAVAILABLE,
            value=value,
            evidence_refs=evidence,
            rule_id=rule_id,
            explanation=f"MFAV status {mfav.status.value}; factor vector not defined.",
            limitations=limitations,
            warnings=list(mfav.classification_warnings)[:5],
        )

    kind, reason = _validate_mfav_factor_profile(mfav)
    if kind == "unavailable":
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.UNAVAILABLE,
            value=value,
            evidence_refs=evidence,
            rule_id=rule_id,
            explanation=reason or "Required MFAV factor evidence unavailable.",
            limitations=limitations,
            warnings=list(mfav.classification_warnings)[:5],
        )
    if kind == "contradicted":
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.CONTRADICTED,
            value=value,
            evidence_refs=evidence,
            rule_id=rule_id,
            explanation=reason or "MFAV factor profile evidence contradicted.",
            limitations=limitations,
            warnings=list(mfav.classification_warnings)[:5],
        )

    if mfav.status in (MFAVStatus.INCOMPLETE, MFAVStatus.OVERRIDDEN) or not mfav.complete:
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.INCOMPLETE,
            value=value,
            evidence_refs=evidence,
            rule_id=rule_id,
            explanation=f"MFAV status {mfav.status.value}; profile incomplete or overridden.",
            limitations=limitations,
            warnings=list(mfav.classification_warnings)[:5],
        )

    if mfav.status == MFAVStatus.COMPLETE and mfav.normalized_factor_vector is not None:
        return DimensionResult(
            dimension_id="factor_profile",
            status=AssuranceStatus.VERIFIED,
            value=value,
            evidence_refs=evidence,
            rule_id=rule_id,
            explanation=(
                "MFAV factor profile validated: event assignments, per-factor aggregation, "
                "raw totals, normalized vector, and conservation_error are consistent."
            ),
            limitations=limitations,
            warnings=list(mfav.classification_warnings)[:5],
        )

    return DimensionResult(
        dimension_id="factor_profile",
        status=AssuranceStatus.UNAVAILABLE,
        value=value,
        evidence_refs=evidence,
        rule_id=rule_id,
        explanation=f"MFAV status {mfav.status.value}; cannot verify factor profile.",
        limitations=limitations,
        warnings=list(mfav.classification_warnings)[:5],
    )


def evaluate_audit_integrity(
    plhc_result: Optional[IntegrityVerificationResult],
) -> DimensionResult:
    """
    Map a PLHC verification result into the Assurance Profile (rule v1).

    Local hash verification is not immutability or independent trust.
    """
    limitations = [
        "PLHC verification is tamper-evident relative to a retained checkpoint only.",
        "Does not imply immutability, external anchoring, or causal validity.",
        "No PLHC result → unavailable (never invented as verified).",
    ]
    if plhc_result is None:
        return DimensionResult(
            dimension_id="audit_integrity",
            status=AssuranceStatus.UNAVAILABLE,
            value=None,
            rule_id="assurance.audit_integrity.v1",
            explanation="No PLHC IntegrityVerificationResult provided.",
            limitations=limitations,
        )

    value = {
        "plhc_status": plhc_result.status.value,
        "merkle_root": (
            None
            if plhc_result.snapshot is None
            else plhc_result.snapshot.merkle_root
        ),
        "leaf_count": (
            None
            if plhc_result.snapshot is None
            else plhc_result.snapshot.leaf_count
        ),
        "checkpoint_hash": (
            None
            if plhc_result.checkpoint is None
            else plhc_result.checkpoint.checkpoint_hash
        ),
        "diagnostics": list(plhc_result.diagnostics)[:12],
    }
    evidence: list[str] = []
    if plhc_result.snapshot is not None:
        evidence.append(plhc_result.snapshot.merkle_root)
    if plhc_result.checkpoint is not None:
        evidence.append(plhc_result.checkpoint.checkpoint_hash)

    mapping = {
        IntegrityStatus.VERIFIED: AssuranceStatus.VERIFIED,
        IntegrityStatus.CONTRADICTED: AssuranceStatus.CONTRADICTED,
        IntegrityStatus.INCOMPLETE: AssuranceStatus.INCOMPLETE,
        IntegrityStatus.UNAVAILABLE: AssuranceStatus.UNAVAILABLE,
    }
    status = mapping.get(plhc_result.status, AssuranceStatus.UNAVAILABLE)
    return DimensionResult(
        dimension_id="audit_integrity",
        status=status,
        value=value,
        evidence_refs=evidence,
        rule_id="assurance.audit_integrity.v1",
        explanation=plhc_result.explanation,
        limitations=limitations + list(plhc_result.limitations)[:4],
        warnings=list(plhc_result.diagnostics)[:5],
    )
