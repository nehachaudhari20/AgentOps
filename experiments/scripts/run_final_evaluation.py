#!/usr/bin/env python3
"""
Phase 2.11 statistical evaluation over Phase 2.10 comparison artifacts + RQ live checks.

Does not retune methods. Writes machine-readable results under experiments/results/final_evaluation/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.evaluation.compare import run_catalog
from agenttrust.evaluation.rq_analysis import (
    aggregate_comparison_file,
    rq1_lineage_fidelity,
    rq4_assurance_summary,
    rq5_plhc,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=ROOT / "data" / "benchmarks" / "experimental_2_9",
    )
    p.add_argument(
        "--comparison-root",
        type=Path,
        default=ROOT / "experiments" / "results" / "phase_2_10",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments" / "results" / "final_evaluation",
    )
    p.add_argument(
        "--splits",
        nargs="+",
        default=["development", "validation", "heldout_test"],
    )
    p.add_argument("--limit", type=int, default=None, help="Optional per-split cap")
    p.add_argument("--rq4-limit", type=int, default=80)
    p.add_argument("--rq5-limit", type=int, default=40)
    p.add_argument("--skip-rerun-comparison", action="store_true")
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    args.comparison_root.mkdir(parents=True, exist_ok=True)

    fingerprints = {}
    design = args.dataset_root / "design_fingerprint.json"
    if design.is_file():
        fingerprints["design"] = json.loads(design.read_text(encoding="utf-8"))

    all_rq = {}
    for split in args.splits:
        sdir = args.dataset_root / "splits" / split
        comp_path = args.comparison_root / f"{split}_comparison.json"
        if not args.skip_rerun_comparison or not comp_path.is_file():
            print(f"Comparison run: {split}", flush=True)
            run_catalog(
                sdir,
                limit=args.limit,
                include_shapley=False,
                out_path=comp_path,
            )
        print(f"RQ aggregate: {split}", flush=True)
        agg = aggregate_comparison_file(comp_path)
        rq1 = rq1_lineage_fidelity(sdir, limit=args.limit)
        rq4 = rq4_assurance_summary(sdir, limit=args.rq4_limit)
        rq5 = rq5_plhc(sdir, limit=args.rq5_limit)
        split_out = {
            "split": split,
            "dataset_fingerprint": None,
            "rq1": rq1,
            "rq2": agg["rq2"],
            "rq3": agg["rq3"],
            "rq4": rq4,
            "rq5": rq5,
            "comparison_source": str(comp_path.as_posix()),
            "n_examined": agg.get("n_examined"),
            "n_failed": agg.get("n_failed"),
        }
        fp_path = sdir / "fingerprint_manifest.json"
        if fp_path.is_file():
            split_out["dataset_fingerprint"] = json.loads(fp_path.read_text(encoding="utf-8")).get(
                "corpus_fingerprint_sha256"
            )
        all_rq[split] = split_out
        (args.out / f"{split}_rq_summary.json").write_text(
            json.dumps(split_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    master = {
        "plan": "docs/methodology/STATISTICAL_ANALYSIS_PLAN.md",
        "protocol": "docs/methodology/BASELINE_AND_ABLATION_PROTOCOL.md",
        "design_fingerprint": fingerprints.get("design"),
        "splits": all_rq,
        "confirmatory_split": "heldout_test",
        "notes": [
            "Trace is the experimental unit.",
            "Shapley omitted from bulk run (offline; enable separately).",
            "B3 Markov not independently implemented.",
        ],
    }
    (args.out / "final_rq_master.json").write_text(
        json.dumps(master, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: {"n": v.get("n_examined"), "rq3": v["rq3"].get("delta_p2_minus_p1")} for k, v in all_rq.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
