#!/usr/bin/env python3
"""
Generate Phase 2.9 experimental dataset splits (development / validation / heldout_test).

Does not overwrite data/benchmarks/pilot/.
Does not commit. Failures are recorded with denominators — not silently skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark.dataset import (
    DEFAULT_ROOT,
    DatasetSplit,
    aggregate_statistics,
    generate_split,
    validate_split,
    write_design_and_reports,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        type=Path,
        default=ROOT / DEFAULT_ROOT,
        help="Dataset root (default: data/benchmarks/experimental_2_9)",
    )
    p.add_argument(
        "--split",
        choices=[s.value for s in DatasetSplit] + ["all"],
        default="all",
    )
    p.add_argument("--force", action="store_true", help="Regenerate even if catalog exists")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on specs per split (smoke tests)",
    )
    p.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip post-generation validation pass",
    )
    args = p.parse_args(argv)

    write_design_and_reports(args.root)
    splits = list(DatasetSplit) if args.split == "all" else [DatasetSplit(args.split)]
    results = []
    any_fail = False
    for split in splits:
        print(f"Generating {split.value} ...", flush=True)
        res = generate_split(split, root=args.root, force=args.force, limit=args.limit)
        results.append(
            {
                "split": res.split,
                "n_planned": res.n_planned,
                "n_written": res.n_written,
                "n_skipped_existing": res.n_skipped_existing,
                "n_failed": res.n_failed,
                "failures": res.failures[:20],
                "catalog_path": res.catalog_path,
            }
        )
        print(
            json.dumps(
                {
                    "split": res.split,
                    "planned": res.n_planned,
                    "written": res.n_written,
                    "skipped": res.n_skipped_existing,
                    "failed": res.n_failed,
                }
            ),
            flush=True,
        )
        if res.n_failed:
            any_fail = True
        if not args.skip_validate and (res.n_written or res.n_skipped_existing):
            # Full fingerprint; sample package checks (all if small)
            v = validate_split(args.root / "splits" / split.value)
            results[-1]["validation_ok"] = v["ok"]
            results[-1]["validation_errors"] = v["errors"][:20]
            if not v["ok"]:
                any_fail = True

    stats = aggregate_statistics(args.root)
    reports = args.root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "generation_run.json").write_text(
        json.dumps({"results": results, "statistics": stats}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "dataset_statistics.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "split_coverage.json").write_text(
        json.dumps({k: v for k, v in stats.get("splits", {}).items()}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"statistics": stats, "any_fail": any_fail}, indent=2))
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
