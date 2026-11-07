"""
RQ aggregations (Phase 2.11 + 2.13 research-validity corrections).

RQ1 = fidelity of MLPG reconstruction against simulator-declared lineage
      (NOT independent real-world lineage recovery).
RQ4 = diagnostic Assurance evaluation with observability-aware eligibility.
RQ5 = stratified PLHC attack evaluation with Wilson CIs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from agenttrust.benchmark.dataset.observability import ObservabilityClass, primary_class
from agenttrust.benchmark.dataset.power import mcnemar_exact_pvalue
from agenttrust.evaluation.compare import load_trace_package
from agenttrust.evaluation.gt_access import (
    intervention_agent_reference_for_outcome,
    lineage_edge_sets,
    load_ground_truth,
)
from agenttrust.evaluation.metrics import (
    cliffs_delta,
    confusion_rates,
    edge_prf,
    holm_correct,
    mean_ci_bootstrap,
    paired_cliffs_delta,
    paired_mean_diff_ci,
    paired_standardized_mean_diff,
)
from agenttrust.evaluation.plhc_attacks import evaluate_plhc_attacks
from agenttrust.evaluation.sampling import stratified_sample_entries, wilson_ci
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import RelationshipType


def _mlpg_edge_sets(trace: ProvenanceTrace) -> dict[str, set[tuple[str, str]]]:
    g = trace.graph
    depends: set[tuple[str, str]] = set()
    produces: set[tuple[str, str]] = set()
    consumes: set[tuple[str, str]] = set()
    for u, v, _, data in g.edges(keys=True, data=True):
        rt = data.get("rel_type")
        if rt == RelationshipType.DEPENDS_ON.value:
            depends.add((u, v))
        elif rt == RelationshipType.PRODUCES.value:
            produces.add((u, v))
        elif rt == RelationshipType.CONSUMES.value:
            consumes.add((u, v))
    return {"DEPENDS_ON": depends, "PRODUCES": produces, "CONSUMES": consumes}


def rq1_lineage_fidelity(
    split_dir: Path,
    *,
    limit: Optional[int] = None,
    seed: int = 2_13_101,
    include_negative_diagnostics: bool = True,
) -> dict[str, Any]:
    """
    Fidelity of MLPG reconstruction vs simulator-declared lineage GT.

    Does NOT establish independent real-world lineage recovery.
    """
    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    entries = cat.get("entries", [])
    sample = stratified_sample_entries(entries, n=limit, seed=seed)
    selected = sample["entries"]

    f1_dep, f1_prod, f1_cons = [], [], []
    per_topo: dict[str, list[float]] = defaultdict(list)
    per_rel = {
        "DEPENDS_ON": {"precision": [], "recall": [], "f1": []},
        "PRODUCES": {"precision": [], "recall": [], "f1": []},
        "CONSUMES": {"precision": [], "recall": [], "f1": []},
    }
    ineligible: list[dict[str, str]] = []
    n_ok = 0
    for e in selected:
        tid = e["trace_id"]
        try:
            pt, _ = load_trace_package(split_dir / "traces" / tid)
            gt = load_ground_truth(split_dir / "ground_truth" / f"{tid}.json")
        except Exception as exc:  # noqa: BLE001 — record ineligible
            ineligible.append({"trace_id": tid, "reason": f"load_failed:{type(exc).__name__}"})
            continue
        pred = _mlpg_edge_sets(pt)
        ref = lineage_edge_sets(gt)
        scores = {}
        for rel in ("DEPENDS_ON", "PRODUCES", "CONSUMES"):
            s = edge_prf(pred[rel], ref[rel])
            scores[rel] = s
            per_rel[rel]["precision"].append(s["precision"])
            per_rel[rel]["recall"].append(s["recall"])
            per_rel[rel]["f1"].append(s["f1"])
        f1_dep.append(scores["DEPENDS_ON"]["f1"])
        f1_prod.append(scores["PRODUCES"]["f1"])
        f1_cons.append(scores["CONSUMES"]["f1"])
        topo = e.get("topology_id") or gt.structural.topology_id or "unknown"
        per_topo[str(topo)].append(scores["DEPENDS_ON"]["f1"])
        n_ok += 1

    negative = None
    if include_negative_diagnostics:
        negative = _rq1_negative_relationship_cases()

    return {
        "rq": "RQ1",
        "endpoint_definition": (
            "Fidelity of MLPG reconstruction against simulator-declared lineage"
        ),
        "not_claimed": "Independent real-world lineage recovery",
        "n_traces": n_ok,
        "n_ineligible": len(ineligible),
        "ineligible": ineligible,
        "sampling": {k: v for k, v in sample.items() if k != "entries"},
        "depends_on_f1": mean_ci_bootstrap(f1_dep, seed=11),
        "produces_f1": mean_ci_bootstrap(f1_prod, seed=12),
        "consumes_f1": mean_ci_bootstrap(f1_cons, seed=13),
        "per_relationship": {
            rel: {
                "precision": mean_ci_bootstrap(vals["precision"], seed=100 + i),
                "recall": mean_ci_bootstrap(vals["recall"], seed=200 + i),
                "f1": mean_ci_bootstrap(vals["f1"], seed=300 + i),
            }
            for i, (rel, vals) in enumerate(per_rel.items())
        },
        "per_topology_depends_f1": {
            t: mean_ci_bootstrap(vs, seed=40 + i) for i, (t, vs) in enumerate(sorted(per_topo.items()))
        },
        "negative_relationship_diagnostics": negative,
        "note": (
            "Synthetic oracle agreement measures reconstruction fidelity vs generator "
            "declarations, not production validity."
        ),
    }


def _rq1_neg_event(
    eid: str,
    *,
    deps: list[str] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": eid,
        "trace_id": "rq1neg",
        "event_type": "reasoning",
        "category": "reasoning",
        "agent_id": "a",
        "status": "success",
        "ts_start": "2020-01-01T00:00:00+00:00",
        "ts_end": "2020-01-01T00:00:01+00:00",
        "dependency_event_ids": list(deps or []),
        "input_artifact_ids": list(inputs or []),
        "output_artifact_ids": list(outputs or []),
        "schema_version": "2.1.0",
    }


def _rq1_negative_relationship_cases() -> dict[str, Any]:
    """Synthetic negative cases for relationship fidelity diagnostics."""
    import hashlib

    def art(aid: str, content: str) -> dict[str, Any]:
        return {
            "artifact_id": aid,
            "artifact_type": "document",
            "content_hash": "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            "schema_version": "2.1.0",
        }

    cases = []
    arts = [art("ax", "x")]
    events = [_rq1_neg_event("e1", outputs=["ax"]), _rq1_neg_event("e2", inputs=["ax"])]
    pt = ProvenanceTrace()
    pt.load_records(events, arts)
    pred = _mlpg_edge_sets(pt)
    ref_missing = {"DEPENDS_ON": {("e1", "e2")}, "PRODUCES": {("e1", "ax")}, "CONSUMES": {("ax", "e2")}}
    cases.append(
        {
            "case": "missing_depends_on",
            "score": edge_prf(pred["DEPENDS_ON"], ref_missing["DEPENDS_ON"]),
        }
    )
    events2 = [
        _rq1_neg_event("e1", outputs=["ax"]),
        _rq1_neg_event("e2", deps=["e1"], inputs=["ax"]),
        _rq1_neg_event("e3"),
    ]
    pt2 = ProvenanceTrace()
    pt2.load_records(events2, arts)
    pred2 = _mlpg_edge_sets(pt2)
    ref_wrong = {"DEPENDS_ON": {("e1", "e3")}, "PRODUCES": set(), "CONSUMES": set()}
    cases.append(
        {
            "case": "incorrect_endpoint",
            "score": edge_prf(pred2["DEPENDS_ON"], ref_wrong["DEPENDS_ON"]),
        }
    )
    cases.append(
        {
            "case": "duplicate_edges_set_semantics",
            "score": edge_prf({("e1", "e2"), ("e1", "e2")}, {("e1", "e2")}),
        }
    )
    cases.append(
        {
            "case": "incorrect_relationship_type",
            "score": edge_prf(pred["DEPENDS_ON"], pred["PRODUCES"]),
            "note": "Type confusion caught by per-relationship scoring",
        }
    )
    return {"cases": cases, "purpose": "negative/edge-case diagnostics; not corpus aggregate"}


def _collect_method_scores(comparison: dict[str, Any], method_id: str) -> list[float]:
    vals = []
    n_failed = 0
    n_unscored = 0
    for tr in comparison.get("traces", []):
        for row in tr.get("rows", []):
            if row.get("allocation", {}).get("method_id") != method_id:
                continue
            sc = row.get("score") or {}
            if not sc.get("scored"):
                n_unscored += 1
                continue
            mae = sc.get("mae")
            if mae != mae:
                n_failed += 1
                continue
            vals.append(float(mae))
    return vals  # caller tracks denominators from comparison


def rq2_attribution(comparison: dict[str, Any]) -> dict[str, Any]:
    methods = [
        "rpa_p1",
        "rpa_p2",
        "B0_uniform_agent",
        "B1_last_touch",
        "B2_p1_equal_share",
        "B4_shapley",
    ]
    out: dict[str, Any] = {
        "rq": "RQ2",
        "methods": {},
        "n_traces_examined": comparison.get("n_examined"),
        "n_failed_methods_recorded": comparison.get("n_failed"),
        "reference_disclosure": (
            "Primary scored reference equal_root_ancestor_mass.v1 is structurally aligned "
            "with ConservedRPA alpha=0. Zero MAE is NOT independent attribution accuracy. "
            "B2_p1_equal_share is an alias of RPA-P1. B3 Markov is not independently implemented."
        ),
        "intervention_reference_status": (
            "intervention_participation_mass.v1 available via evaluate_intervention_attribution; "
            "undefined on clean traces without interventions."
        ),
    }
    for m in methods:
        vals = _collect_method_scores(comparison, m)
        out["methods"][m] = {
            "mae": mean_ci_bootstrap(vals, seed=20),
            "n_scored": len(vals),
            "information_budget": (
                "offline_combinatorial"
                if m == "B4_shapley"
                else ("alias_of_rpa_p1" if m == "B2_p1_equal_share" else "online_evidence")
            ),
        }
    return out


def evaluate_intervention_attribution(
    split_dir: Path,
    *,
    limit: Optional[int] = None,
    seed: int = 2_13_201,
) -> dict[str, Any]:
    """
    Score ConservedRPA / baselines against intervention_participation_mass.v1.

    Only fault traces with defined intervention agent mass are eligible.
    """
    from agenttrust.evaluation.baselines import (
        allocate_b0_uniform,
        allocate_b1_last_touch,
        allocate_rpa,
    )
    from agenttrust.evaluation.compare import score_allocation

    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    sample = stratified_sample_entries(cat.get("entries", []), n=limit, seed=seed)
    method_scores: dict[str, list[float]] = defaultdict(list)
    n_defined = n_undefined = n_failed = 0
    for e in sample["entries"]:
        tid = e["trace_id"]
        pt, _ = load_trace_package(split_dir / "traces" / tid)
        gt = load_ground_truth(split_dir / "ground_truth" / f"{tid}.json")
        outcomes = pt.outcome_candidates()[:1]
        if not outcomes:
            n_failed += 1
            continue
        oid = outcomes[0]
        truth = intervention_agent_reference_for_outcome(gt, oid, events=[ev.to_public_dict() for ev in pt.events])
        if truth is None:
            n_undefined += 1
            continue
        n_defined += 1
        suite = [
            allocate_rpa(pt, oid, projection_kind=ProjectionKind.P1_DIRECT, method_id="rpa_p1"),
            allocate_rpa(pt, oid, projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE, method_id="rpa_p2"),
            allocate_b0_uniform(pt, oid),
            allocate_b1_last_touch(pt, oid),
        ]
        for res in suite:
            sc = score_allocation(res, truth)
            if sc.get("scored"):
                method_scores[res.method_id].append(float(sc["mae"]))
            else:
                n_failed += 1

    return {
        "reference_method": "intervention_participation_mass.v1",
        "n_defined": n_defined,
        "n_undefined": n_undefined,
        "n_failed": n_failed,
        "sampling": {k: v for k, v in sample.items() if k != "entries"},
        "methods": {
            m: {"mae": mean_ci_bootstrap(vs, seed=50 + i), "n_scored": len(vs)}
            for i, (m, vs) in enumerate(sorted(method_scores.items()))
        },
        "disclaimer": (
            "Intervention participation mass is planted-simulator semantics, not causal/"
            "legal responsibility. Attribution accuracy RQ remains limited if defined n is small."
        ),
        "inconclusive_if": "n_defined == 0 or reference structurally insufficient",
    }


def rq3_p2_vs_p1(comparison: dict[str, Any]) -> dict[str, Any]:
    deltas_all, deltas_bridge, deltas_no = [], [], []
    p1, p2 = [], []
    n_bridge_traces = 0
    for tr in comparison.get("traces", []):
        paired = tr.get("paired_p1_p2")
        if not paired:
            continue
        d = float(paired["delta_p2_minus_p1"])
        deltas_all.append(d)
        p1.append(float(paired["mae_p1"]))
        p2.append(float(paired["mae_p2"]))
        if paired.get("has_artifact_bridge"):
            deltas_bridge.append(d)
            n_bridge_traces += 1
        else:
            deltas_no.append(d)
    return {
        "rq": "RQ3",
        "n_paired": len(deltas_all),
        "n_with_artifact_bridge_edges": n_bridge_traces,
        "delta_p2_minus_p1": mean_ci_bootstrap(deltas_all, seed=31),
        "paired_mean_diff_ci": paired_mean_diff_ci(p2, p1, seed=34),
        "paired_cliffs_delta": paired_cliffs_delta(p2, p1),
        "paired_standardized_mean_diff": paired_standardized_mean_diff(p2, p1),
        "unpaired_cliffs_delta_exploratory_only": cliffs_delta(p2, p1),
        "delta_with_bridges": mean_ci_bootstrap(deltas_bridge, seed=32),
        "delta_without_bridges": mean_ci_bootstrap(deltas_no, seed=33),
        "practical_threshold_abs": 0.02,
        "interpretation_note": (
            "Negative mean Δ favors P2 (lower MAE). Phase 2.9 corpus often has "
            "DEPENDS_ON covering artifact paths → bridge subgroup may be empty; "
            "see experimental_2_13_bridges for distinguishable P1/P2 graphs. "
            "Do not claim P2 superiority without bridge-eligible evidence."
        ),
        "reference_limitation": (
            "MAE vs equal_root reference is non-discriminative for RPA α=0 alignment."
        ),
    }


def rq4_assurance_summary(
    split_dir: Path,
    *,
    limit: Optional[int] = None,
    seed: int = 2_13_401,
) -> dict[str, Any]:
    """
    Assurance diagnostic evaluation with observability-aware eligibility.

    Trace-completeness remains a separately named endpoint. Unobservable faults
    are excluded from ordinary false-negative denominators.
    """
    from agenttrust import AssuranceProfileCalculator, ConservedRPA, MFAV, PLHC
    from agenttrust.attribution.rpa import RPAError

    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    sample = stratified_sample_entries(cat.get("entries", []), n=limit, seed=seed)
    selected = sample["entries"]

    # Completeness endpoint
    tp = fp = tn = fn = 0
    # Observability-aware fault observability diagnostic (structural dims)
    by_obs: dict[str, dict[str, int]] = defaultdict(lambda: {"eligible": 0, "flagged": 0, "excluded": 0})
    by_fault: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "flagged": 0, "excluded": 0})
    by_topo: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "flagged": 0})
    excluded_unobs = 0
    calc = AssuranceProfileCalculator()

    for e in selected:
        tid = e["trace_id"]
        pt, _ = load_trace_package(split_dir / "traces" / tid)
        gt = load_ground_truth(split_dir / "ground_truth" / f"{tid}.json")
        # Prediction first — GT used only after
        rpa = None
        mfav = None
        try:
            rpa = ConservedRPA().allocate_from_trace(pt, projection_kind=ProjectionKind.P1_DIRECT)[0]
            mfav = MFAV().compute(rpa, trace=pt)
        except RPAError:
            pass
        plhc = PLHC()
        snap = plhc.build_snapshot(pt)
        cp = plhc.create_checkpoint(snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00")
        plhc_res = plhc.verify_against_checkpoint(pt, cp)
        profile = calc.compute(pt, rpa_result=rpa, mfav_result=mfav, plhc_result=plhc_res)

        dim_status = {
            name: dim.status.value for name, dim in profile.dimensions.items()
        }
        completeness_flagged = dim_status.get("trace_completeness") in (
            "incomplete",
            "contradicted",
        )
        any_structural_flag = any(
            dim_status.get(d) in ("incomplete", "contradicted", "inconsistent", "unavailable")
            for d in (
                "trace_completeness",
                "reference_integrity",
                "identity_coverage",
                "temporal_consistency",
            )
        )

        planted_inc = bool(gt.quality.intentionally_incomplete)
        if planted_inc and completeness_flagged:
            tp += 1
        elif planted_inc and not completeness_flagged:
            fn += 1
        elif (not planted_inc) and completeness_flagged:
            fp += 1
        else:
            tn += 1

        faults = list(e.get("fault_types") or [])
        topo = str(e.get("topology_id") or "unknown")
        by_topo[topo]["n"] += 1
        if any_structural_flag:
            by_topo[topo]["flagged"] += 1

        if not faults:
            obs = "clean"
            by_obs[obs]["eligible"] += 1
            if any_structural_flag:
                by_obs[obs]["flagged"] += 1
        else:
            for ft in faults:
                by_fault[ft]["n"] += 1
                try:
                    obs = primary_class(ft)
                except KeyError:
                    obs = "unknown"
                if obs == ObservabilityClass.NOT_RELIABLY_DETECTABLE.value:
                    by_obs[obs]["excluded"] += 1
                    by_fault[ft]["excluded"] += 1
                    excluded_unobs += 1
                    continue
                if obs == ObservabilityClass.REQUIRES_GROUND_TRUTH.value:
                    # Eligible for GT-aware diagnostic reporting only — not ordinary FN
                    by_obs[obs]["eligible"] += 1
                    if any_structural_flag:
                        by_obs[obs]["flagged"] += 1
                        by_fault[ft]["flagged"] += 1
                    continue
                by_obs[obs]["eligible"] += 1
                if any_structural_flag:
                    by_obs[obs]["flagged"] += 1
                    by_fault[ft]["flagged"] += 1

    rates = confusion_rates(tp, fp, tn, fn)
    det_ci = wilson_ci(tp, tp + fn) if (tp + fn) else wilson_ci(0, 0)
    far_ci = wilson_ci(fp, fp + tn) if (fp + tn) else wilson_ci(0, 0)

    return {
        "rq": "RQ4",
        "terminology": "diagnostic_capability_not_fraud_or_trustworthiness",
        "trace_completeness_endpoint": {
            "dimension": "trace_completeness_vs_intentional_incompleteness",
            **rates,
            "detection_rate_wilson": det_ci,
            "false_alarm_rate_wilson": far_ci,
        },
        "observability_aware": {
            "by_observability_class": dict(by_obs),
            "by_fault_family": dict(by_fault),
            "by_topology": dict(by_topo),
            "excluded_not_reliably_detectable": excluded_unobs,
            "note": (
                "not_reliably_detectable faults are excluded from ordinary Assurance "
                "false-negative denominators. requires_ground_truth faults are reported "
                "separately and are not counted as ordinary online false negatives."
            ),
        },
        "n_traces": len(selected),
        "sampling": {k: v for k, v in sample.items() if k != "entries"},
        "caveat": (
            "RQ4 does not establish comprehensive fault detection. "
            "It reports diagnostic signals under declared observability classes."
        ),
    }


def rq5_plhc(
    split_dir: Path,
    *,
    limit: Optional[int] = None,
    seed: int = 2_13_501,
) -> dict[str, Any]:
    """
    Stratified PLHC attack evaluation with per-attack Wilson CIs.

    Threat model: tamper-evident vs honestly retained checkpoint.
    """
    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    sample = stratified_sample_entries(cat.get("entries", []), n=limit, seed=seed)
    selected = sample["entries"]

    clean_ok = 0
    attack_detect: dict[str, list[bool]] = defaultdict(list)
    for e in selected:
        pt, _ = load_trace_package(split_dir / "traces" / e["trace_id"])
        rep = evaluate_plhc_attacks(pt)
        if rep["clean_control"]["ok"]:
            clean_ok += 1
        for name, row in rep["attacks"].items():
            attack_detect[name].append(bool(row["detected"]))

    n = len(selected)
    per_attack = {}
    for k, v in sorted(attack_detect.items()):
        det = sum(1 for x in v if x)
        per_attack[k] = {
            "n_tested": len(v),
            "n_detected": det,
            "detection_rate": det / len(v) if v else float("nan"),
            "wilson_95": wilson_ci(det, len(v)),
        }

    return {
        "rq": "RQ5",
        "n_traces": n,
        "sampling": {k: v for k, v in sample.items() if k != "entries"},
        "clean_verified_rate": wilson_ci(clean_ok, n) if n else wilson_ci(0, 0),
        "false_reject_rate": wilson_ci(n - clean_ok, n) if n else wilson_ci(0, 0),
        "per_attack": per_attack,
        "threat_model": (
            "tamper-evident relative to honestly retained checkpoint; "
            "NOT immutability; NOT external anchoring; NOT dual-rewrite resistant"
        ),
        "not_claimed": ["immutability", "external_anchoring", "dual_rewrite_protection"],
    }


def aggregate_comparison_file(path: Path) -> dict[str, Any]:
    comparison = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "source": str(path.as_posix()),
        "rq2": rq2_attribution(comparison),
        "rq3": rq3_p2_vs_p1(comparison),
        "n_failed": comparison.get("n_failed"),
        "n_examined": comparison.get("n_examined"),
    }


def confirmatory_holm_bundle(
    *,
    mcnemar_b: int,
    mcnemar_c: int,
    paired_delta_p: Optional[float] = None,
) -> dict[str, Any]:
    """Prespecified confirmatory family with Holm correction (exploratory separate)."""
    tests = [("mcnemar_incompleteness_pairs", mcnemar_exact_pvalue(mcnemar_b, mcnemar_c))]
    if paired_delta_p is not None:
        tests.append(("paired_p2_p1_exploratory_excluded", float(paired_delta_p)))
    # Only McNemar is confirmatory by SAP; if second included mark exploratory
    confirmatory = [("mcnemar_incompleteness_pairs", tests[0][1])]
    return {
        "confirmatory_holm": holm_correct(confirmatory),
        "exploratory_raw": {k: v for k, v in tests[1:]},
        "family": "primary_incompleteness_mcnemar",
    }
