#!/usr/bin/env python3
"""
Phase 2.10 baseline/ablation comparison runner.

Default: development then validation. Pass --heldout only after configs are locked.
Does not tune methods against held-out results.
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
from agenttrust.evaluation.plhc_attacks import evaluate_plhc_attacks
from agenttrust.evaluation.compare import load_trace_package


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--split",
        choices=["development", "validation", "heldout_test", "all_preheldout"],
        default="all_preheldout",
    )
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=ROOT / "data" / "benchmarks" / "experimental_2_9",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments" / "results" / "phase_2_10",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--include-shapley", action="store_true")
    p.add_argument("--plhc-sample", type=int, default=20, help="Traces for PLHC attack sample")
    args = p.parse_args(argv)

    if args.split == "all_preheldout":
        splits = ["development", "validation"]
    else:
        splits = [args.split]

    args.out.mkdir(parents=True, exist_ok=True)
    summaries = {}
    any_fail = False
    for split in splits:
        sdir = args.dataset_root / "splits" / split
        out = args.out / f"{split}_comparison.json"
        print(f"Running comparison on {split} ...", flush=True)
        summary = run_catalog(
            sdir,
            limit=args.limit,
            include_shapley=args.include_shapley,
            out_path=out,
        )
        summaries[split] = {
            "n_examined": summary["n_examined"],
            "n_ok": summary["n_ok"],
            "n_failed": summary["n_failed"],
            "output": str(out.as_posix()),
        }
        if summary["n_failed"]:
            any_fail = True

        # PLHC attack sample
        cat = json.loads((sdir / "catalog.json").read_text(encoding="utf-8"))
        plhc_rows = []
        for e in cat.get("entries", [])[: args.plhc_sample]:
            pt, _ = load_trace_package(sdir / "traces" / e["trace_id"])
            plhc_rows.append({"trace_id": e["trace_id"], **evaluate_plhc_attacks(pt)})
        plhc_path = args.out / f"{split}_plhc_attacks.json"
        plhc_path.write_text(
            json.dumps({"split": split, "n": len(plhc_rows), "results": plhc_rows}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        summaries[split]["plhc_attacks"] = str(plhc_path.as_posix())

    (args.out / "run_summary.json").write_text(
        json.dumps(
            {
                "summaries": summaries,
                "include_shapley": args.include_shapley,
                "note": "Held-out must be run explicitly with --split heldout_test after lock.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summaries, indent=2))
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
