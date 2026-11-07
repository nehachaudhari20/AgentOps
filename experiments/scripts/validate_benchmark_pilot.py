#!/usr/bin/env python3
"""Validate an on-disk Phase 2.4 pilot corpus and optionally run pipeline checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust import ConservedRPA, MFAV, ProvenanceTrace
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth
from agenttrust.benchmark.manifest import TraceManifest
from agenttrust.mlpg.projections import ProjectionKind


def _load_trace_dir(tdir: Path) -> tuple[list, list, TraceManifest, BenchmarkGroundTruth]:
    events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    tid = tdir.name
    pilot = tdir.parent.parent
    man = TraceManifest.from_dict(
        json.loads((pilot / "manifests" / f"{tid}.json").read_text(encoding="utf-8"))
    )
    gt = BenchmarkGroundTruth.from_dict(
        json.loads((pilot / "ground_truth" / f"{tid}.json").read_text(encoding="utf-8"))
    )
    return events, arts, man, gt


def validate_one(tdir: Path, *, run_pipeline: bool) -> dict:
    events, arts, man, gt = _load_trace_dir(tdir)
    errors: list[str] = []
    warnings: list[str] = []

    if man.trace_id != tdir.name:
        errors.append("manifest trace_id != directory name")
    if gt.trace_id != man.trace_id:
        errors.append("ground_truth trace_id mismatch")

    # Ensure GT not embedded as algorithm-facing answer labels in events
    for e in events:
        meta = e.get("metadata") or {}
        if isinstance(meta, dict) and any(k.startswith("gt_") for k in meta):
            errors.append(f"event {e.get('event_id')} contains gt_* metadata")

    pt = ProvenanceTrace()
    pt.load_records(events, arts)
    comp = pt.completeness()

    pipeline = {}
    if run_pipeline and comp.suitable_for_dag_attribution and not comp.incomplete:
        before = pt.fingerprint()
        _ = pt.project(ProjectionKind.P1_DIRECT)
        _ = pt.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
        results = ConservedRPA().allocate_from_trace(pt, projection_kind=ProjectionKind.P1_DIRECT)
        profiles = [MFAV().compute(r, trace=pt) for r in results]
        pipeline = {
            "n_rpa_results": len(results),
            "n_mfav_profiles": len(profiles),
            "fingerprint_unchanged": pt.fingerprint() == before,
        }
        if not pipeline["fingerprint_unchanged"]:
            errors.append("pipeline mutated provenance fingerprint")
    elif run_pipeline:
        warnings.append("skipped RPA/MFAV (incomplete or unsuitable DAG)")

    ok = len(errors) == 0
    return {
        "trace_id": man.trace_id,
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "incomplete": comp.incomplete,
        "pipeline": pipeline,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=ROOT / "data" / "benchmarks" / "pilot",
    )
    parser.add_argument("--pipeline", action="store_true", help="Run P1/P2/RPA/MFAV on complete traces")
    parser.add_argument("--limit", type=int, default=0, help="Optional max traces to check")
    args = parser.parse_args()

    traces_root = args.pilot_root / "traces"
    if not traces_root.exists():
        print(f"No traces at {traces_root}", file=sys.stderr)
        return 1

    dirs = sorted(p for p in traces_root.iterdir() if p.is_dir())
    if args.limit > 0:
        dirs = dirs[: args.limit]

    report = {"n": len(dirs), "failures": [], "results": []}
    for tdir in dirs:
        item = validate_one(tdir, run_pipeline=args.pipeline)
        report["results"].append(item)
        if not item["ok"]:
            report["failures"].append(item)

    out = args.pilot_root / "validation_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"checked={len(dirs)} failures={len(report['failures'])} report={out}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
