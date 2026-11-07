"""
Baseline / ablation comparison runner (Phase 2.10).

Loads algorithm inputs only for method execution; GT used solely for scoring.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from agenttrust.evaluation.baselines import (
    MARKOV_STATUS,
    METHOD_VERSION,
    allocate_b0_uniform,
    allocate_b1_last_touch,
    allocate_b2_p1_equal_share,
    allocate_b4_shapley,
    allocate_rpa,
    run_online_suite,
)
from agenttrust.evaluation.gt_access import agent_reference_for_outcome, load_ground_truth
from agenttrust.evaluation.metrics import mae, rmse, spearman, top_k_agreement, total_variation
from agenttrust.evaluation.schema import AllocationResult
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace

ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0)


def load_trace_package(trace_dir: Path) -> tuple[ProvenanceTrace, str]:
    trace_dir = Path(trace_dir)
    events = json.loads((trace_dir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((trace_dir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    pt = ProvenanceTrace()
    pt.load_records(events, arts, default_trace_id=trace_dir.name)
    return pt, trace_dir.name


def score_allocation(
    result: AllocationResult, truth: Optional[dict[str, float]]
) -> dict[str, Any]:
    if truth is None:
        return {"scored": False, "reason": "missing_gt_reference"}
    if result.status != "ok":
        return {
            "scored": False,
            "reason": f"method_status={result.status}",
            "method_id": result.method_id,
        }
    return {
        "scored": True,
        "method_id": result.method_id,
        "mae": mae(result.agent_allocations, truth),
        "rmse": rmse(result.agent_allocations, truth),
        "spearman": spearman(result.agent_allocations, truth),
        "top1": top_k_agreement(result.agent_allocations, truth, k=1),
        "tv": total_variation(result.agent_allocations, truth),
    }


def evaluate_trace(
    trace_dir: Path,
    gt_path: Path,
    *,
    include_shapley: bool = True,
    primary_outcome_only: bool = True,
    alpha_ablation: bool = True,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    pt, tid = load_trace_package(trace_dir)
    gt = load_ground_truth(gt_path)
    outcomes = pt.outcome_candidates()
    if primary_outcome_only and outcomes:
        outcomes = outcomes[:1]

    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    # P2 bridge presence
    p2 = pt.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    n_bridge = sum(1 for e in p2.edges if e.origin == "ARTIFACT_BRIDGE")

    for oid in outcomes:
        truth = agent_reference_for_outcome(gt, oid)
        if truth is None:
            exclusions.append({"outcome_id": oid, "reason": "no_attribution_reference"})
            continue

        suite = run_online_suite(pt, oid, include_shapley=include_shapley, shapley_seed=gt.seed)
        for res in suite:
            score = score_allocation(res, truth)
            rows.append(
                {
                    "trace_id": tid,
                    "outcome_id": oid,
                    "n_artifact_bridges": n_bridge,
                    "allocation": res.to_dict(),
                    "score": score,
                }
            )

        if alpha_ablation:
            for a in ALPHAS:
                res = allocate_rpa(
                    pt,
                    oid,
                    projection_kind=ProjectionKind.P1_DIRECT,
                    alpha=a,
                    method_id=f"rpa_p1_alpha_{a}",
                )
                rows.append(
                    {
                        "trace_id": tid,
                        "outcome_id": oid,
                        "n_artifact_bridges": n_bridge,
                        "allocation": res.to_dict(),
                        "score": score_allocation(res, truth),
                        "ablation": "A-rpa-alpha",
                    }
                )

    # Paired P1 vs P2 on this trace
    paired = None
    p1_scores = [
        r["score"]["mae"]
        for r in rows
        if r["allocation"]["method_id"] == "rpa_p1" and r["score"].get("scored")
    ]
    p2_scores = [
        r["score"]["mae"]
        for r in rows
        if r["allocation"]["method_id"] == "rpa_p2" and r["score"].get("scored")
    ]
    if p1_scores and p2_scores and len(p1_scores) == len(p2_scores):
        paired = {
            "mae_p1": p1_scores[0],
            "mae_p2": p2_scores[0],
            "delta_p2_minus_p1": p2_scores[0] - p1_scores[0],
            "has_artifact_bridge": n_bridge > 0,
        }

    return {
        "trace_id": tid,
        "provenance_fingerprint": pt.fingerprint(),
        "n_outcomes_considered": len(outcomes),
        "n_rows": len(rows),
        "rows": rows,
        "exclusions": exclusions,
        "paired_p1_p2": paired,
        "markov_status": MARKOV_STATUS,
        "method_version": METHOD_VERSION,
        "timing_ms": {"total": (time.perf_counter() - t0) * 1000.0},
    }


def run_catalog(
    split_dir: Path,
    *,
    limit: Optional[int] = None,
    include_shapley: bool = False,
    out_path: Optional[Path] = None,
) -> dict[str, Any]:
    split_dir = Path(split_dir)
    catalog = json.loads((split_dir / "catalog.json").read_text(encoding="utf-8"))
    entries = list(catalog.get("entries", []))
    if limit is not None:
        entries = entries[: int(limit)]

    results = []
    n_failed = 0
    for e in entries:
        tid = e["trace_id"]
        tdir = split_dir / "traces" / tid
        gt = split_dir / "ground_truth" / f"{tid}.json"
        try:
            results.append(
                evaluate_trace(
                    tdir,
                    gt,
                    include_shapley=include_shapley,
                    primary_outcome_only=True,
                    alpha_ablation=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            n_failed += 1
            results.append({"trace_id": tid, "error": str(exc)})

    summary = {
        "split": catalog.get("split"),
        "design_fingerprint_sha256": catalog.get("design_fingerprint_sha256"),
        "n_catalog": len(catalog.get("entries", [])),
        "n_examined": len(entries),
        "n_ok": sum(1 for r in results if "error" not in r),
        "n_failed": n_failed,
        "method_version": METHOD_VERSION,
        "include_shapley": include_shapley,
        "markov_status": MARKOV_STATUS,
        "traces": results,
    }
    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
