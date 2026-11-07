"""
RQ aggregations for Phase 2.11 from Phase 2.10 comparison artifacts + live checks.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from agenttrust.evaluation.compare import load_trace_package
from agenttrust.evaluation.gt_access import lineage_edge_sets, load_ground_truth
from agenttrust.evaluation.metrics import (
    cliffs_delta,
    edge_prf,
    mean_ci_bootstrap,
    paired_mean_diff_ci,
)
from agenttrust.evaluation.plhc_attacks import evaluate_plhc_attacks
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


def rq1_lineage_fidelity(split_dir: Path, *, limit: Optional[int] = None) -> dict[str, Any]:
    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    entries = cat.get("entries", [])
    if limit is not None:
        entries = entries[:limit]
    f1_dep, f1_prod, f1_cons = [], [], []
    n_ok = 0
    for e in entries:
        tid = e["trace_id"]
        pt, _ = load_trace_package(split_dir / "traces" / tid)
        gt = load_ground_truth(split_dir / "ground_truth" / f"{tid}.json")
        pred = _mlpg_edge_sets(pt)
        ref = lineage_edge_sets(gt)
        d = edge_prf(pred["DEPENDS_ON"], ref["DEPENDS_ON"])
        p = edge_prf(pred["PRODUCES"], ref["PRODUCES"])
        c = edge_prf(pred["CONSUMES"], ref["CONSUMES"])
        f1_dep.append(d["f1"])
        f1_prod.append(p["f1"])
        f1_cons.append(c["f1"])
        n_ok += 1
    return {
        "rq": "RQ1",
        "n_traces": n_ok,
        "depends_on_f1": mean_ci_bootstrap(f1_dep, seed=11),
        "produces_f1": mean_ci_bootstrap(f1_prod, seed=12),
        "consumes_f1": mean_ci_bootstrap(f1_cons, seed=13),
        "note": "Graph construction fidelity vs GT lineage — not causal inference.",
    }


def _collect_method_scores(comparison: dict[str, Any], method_id: str) -> list[float]:
    vals = []
    for tr in comparison.get("traces", []):
        for row in tr.get("rows", []):
            if row.get("allocation", {}).get("method_id") != method_id:
                continue
            sc = row.get("score") or {}
            if sc.get("scored") and sc.get("mae") == sc.get("mae"):
                vals.append(float(sc["mae"]))
    return vals


def rq2_attribution(comparison: dict[str, Any]) -> dict[str, Any]:
    methods = [
        "rpa_p1",
        "rpa_p2",
        "B0_uniform_agent",
        "B1_last_touch",
        "B2_p1_equal_share",
        "B4_shapley",
    ]
    out = {"rq": "RQ2", "methods": {}, "n_traces_examined": comparison.get("n_examined")}
    for m in methods:
        vals = _collect_method_scores(comparison, m)
        out["methods"][m] = {
            "mae": mean_ci_bootstrap(vals, seed=20),
            "n_scored": len(vals),
            "information_budget": (
                "offline_combinatorial"
                if m == "B4_shapley"
                else ("alias" if m == "B2_p1_equal_share" else "online_evidence")
            ),
        }
    return out


def rq3_p2_vs_p1(comparison: dict[str, Any]) -> dict[str, Any]:
    deltas_all, deltas_bridge, deltas_no = [], [], []
    for tr in comparison.get("traces", []):
        paired = tr.get("paired_p1_p2")
        if not paired:
            continue
        d = float(paired["delta_p2_minus_p1"])
        deltas_all.append(d)
        if paired.get("has_artifact_bridge"):
            deltas_bridge.append(d)
        else:
            deltas_no.append(d)
    p1 = [tr["paired_p1_p2"]["mae_p1"] for tr in comparison.get("traces", []) if tr.get("paired_p1_p2")]
    p2 = [tr["paired_p1_p2"]["mae_p2"] for tr in comparison.get("traces", []) if tr.get("paired_p1_p2")]
    return {
        "rq": "RQ3",
        "n_paired": len(deltas_all),
        "delta_p2_minus_p1": mean_ci_bootstrap(deltas_all, seed=31),
        "delta_with_bridges": mean_ci_bootstrap(deltas_bridge, seed=32),
        "delta_without_bridges": mean_ci_bootstrap(deltas_no, seed=33),
        "cliffs_delta_p2_vs_p1_mae": cliffs_delta(p2, p1),
        "practical_threshold_abs": 0.02,
        "interpretation_note": "Negative mean Δ favors P2 (lower MAE).",
    }


def rq4_assurance_summary(split_dir: Path, *, limit: Optional[int] = None) -> dict[str, Any]:
    """
    Lightweight Assurance diagnostic summary without claiming fraud detection.

    Uses pipeline-style completeness vs GT intentional incompleteness as one
    observable contrast; other faults deferred to observability matrix caveats.
    """
    from agenttrust import AssuranceProfileCalculator, ConservedRPA, MFAV, PLHC
    from agenttrust.attribution.rpa import RPAError
    from agenttrust.mlpg.projections import ProjectionKind

    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    entries = cat.get("entries", [])
    if limit is not None:
        entries = entries[:limit]

    tp = fp = tn = fn = 0
    n = 0
    calc = AssuranceProfileCalculator()
    for e in entries:
        tid = e["trace_id"]
        pt, _ = load_trace_package(split_dir / "traces" / tid)
        gt = load_ground_truth(split_dir / "ground_truth" / f"{tid}.json")
        planted_inc = bool(gt.quality.intentionally_incomplete)
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
        flagged = profile.dimensions["trace_completeness"].status.value in (
            "incomplete",
            "contradicted",
        )
        if planted_inc and flagged:
            tp += 1
        elif planted_inc and not flagged:
            fn += 1
        elif (not planted_inc) and flagged:
            fp += 1
        else:
            tn += 1
        n += 1
    return {
        "rq": "RQ4",
        "dimension": "trace_completeness_vs_intentional_incompleteness",
        "n_traces": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "detection_rate": tp / (tp + fn) if (tp + fn) else float("nan"),
        "false_alarm_rate": fp / (fp + tn) if (fp + tn) else float("nan"),
        "caveat": (
            "Only incompleteness contrast is scored here. Faults classified "
            "not_reliably_detectable are not counted as Assurance failures."
        ),
    }


def rq5_plhc(split_dir: Path, *, limit: int = 50) -> dict[str, Any]:
    split_dir = Path(split_dir)
    cat = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    entries = cat.get("entries", [])[:limit]
    clean_ok = 0
    attack_detect: dict[str, list[bool]] = defaultdict(list)
    for e in entries:
        pt, _ = load_trace_package(split_dir / "traces" / e["trace_id"])
        rep = evaluate_plhc_attacks(pt)
        if rep["clean_control"]["ok"]:
            clean_ok += 1
        for name, row in rep["attacks"].items():
            attack_detect[name].append(bool(row["detected"]))
    return {
        "rq": "RQ5",
        "n_traces": len(entries),
        "clean_verified_rate": clean_ok / len(entries) if entries else float("nan"),
        "false_reject_rate": 1.0 - (clean_ok / len(entries) if entries else float("nan")),
        "attack_detection_rates": {
            k: sum(v) / len(v) if v else float("nan") for k, v in sorted(attack_detect.items())
        },
        "threat_model": "tamper-evident vs retained checkpoint; not immutable/external anchor",
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
