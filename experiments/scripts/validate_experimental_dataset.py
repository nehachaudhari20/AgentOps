#!/usr/bin/env python3
"""Validate Phase 2.9 experimental dataset corpora and write reports."""

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
    validate_cross_split_isolation,
    validate_split,
    write_design_and_reports,
)
from agenttrust.benchmark.dataset.observability import observability_matrix


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT / DEFAULT_ROOT)
    p.add_argument(
        "--max-trace-checks",
        type=int,
        default=None,
        help="Limit per-split package deep checks (default: all)",
    )
    args = p.parse_args(argv)

    write_design_and_reports(args.root)
    reports = args.root / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    split_reports = {}
    ok = True
    for split in DatasetSplit:
        sdir = args.root / "splits" / split.value
        if not (sdir / "catalog.json").is_file():
            split_reports[split.value] = {"ok": False, "errors": ["missing catalog"]}
            ok = False
            continue
        r = validate_split(sdir, max_trace_checks=args.max_trace_checks)
        split_reports[split.value] = r
        if not r["ok"]:
            ok = False

    cross = validate_cross_split_isolation(args.root)
    if not cross["ok"]:
        ok = False
    stats = aggregate_statistics(args.root)

    gt_report = {
        "ok": ok,
        "note": "Attribution references required on experimental GT packages",
        "splits_checked": list(split_reports),
        "cross_split": cross,
    }
    (reports / "ground_truth_validation.json").write_text(
        json.dumps(gt_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "dataset_statistics.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "split_coverage.json").write_text(
        json.dumps(stats.get("splits", {}), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "fault_observability_matrix.json").write_text(
        json.dumps(observability_matrix(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (reports / "validation_summary.json").write_text(
        json.dumps(
            {"ok": ok, "split_reports": {k: {"ok": v.get("ok"), "errors": v.get("errors")} for k, v in split_reports.items()}, "cross": cross},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": ok, "n_traces": stats.get("n_traces_total"), "cross": cross}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
