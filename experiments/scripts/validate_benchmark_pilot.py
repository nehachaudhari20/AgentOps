#!/usr/bin/env python3
"""
Historical Phase 2.4 pilot validation (Mode A).

Validates package consistency, schema load, ground-truth IDs/manifests, and optional
P1/P2/RPA/MFAV pipeline compatibility for the checked-in pilot under
``data/benchmarks/pilot/``.

By default ``--strict-fault-observables`` is OFF: this command does **not** claim that
historical 2.4.0 fault fixtures satisfy Phase 2.5.1 fault-observable semantics.

For strict fresh generator fault validation (Mode B), use:
``python experiments/scripts/validate_phase25_fault_matrix.py``
"""

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
from agenttrust.benchmark.manifest import (
    BenchmarkConfig,
    ScenarioId,
    ScaleTier,
    TopologyId,
    TraceManifest,
)
from agenttrust.benchmark.validation import validate_package
from agenttrust.mlpg.projections import ProjectionKind


def _validate_dir(tdir: Path, pilot_root: Path, *, strict_fault_observables: bool):
    events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    man = TraceManifest.from_dict(
        json.loads((pilot_root / "manifests" / f"{tdir.name}.json").read_text(encoding="utf-8"))
    )
    gt = BenchmarkGroundTruth.from_dict(
        json.loads((pilot_root / "ground_truth" / f"{tdir.name}.json").read_text(encoding="utf-8"))
    )
    try:
        cfg = BenchmarkConfig(
            scenario_id=ScenarioId(man.scenario_id),
            topology_id=TopologyId(man.topology_id),
            scale_tier=ScaleTier(man.scale_tier),
            seed=man.seed,
            fault_types=tuple(man.fault_types),
            incomplete=man.incomplete,
            generator_version=man.generator_version,
        )
    except Exception:
        cfg = None
    return validate_package(
        events=events,
        artifacts=arts,
        manifest=man,
        ground_truth=gt,
        config=cfg,
        require_complete=False,
        load_provenance=True,
        verify_fingerprint=cfg is not None,
        check_fault_observables=strict_fault_observables,
        expected_trace_dirname=tdir.name,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=ROOT / "data" / "benchmarks" / "pilot",
    )
    parser.add_argument("--pipeline", action="store_true", help="Run P1/P2/RPA/MFAV on complete traces")
    parser.add_argument("--limit", type=int, default=0, help="Optional max traces to check")
    parser.add_argument(
        "--strict-fault-observables",
        action="store_true",
        help="Enforce Phase 2.5 fault observable semantics (fails on 2.4.0 planted effects)",
    )
    args = parser.parse_args()

    traces_root = args.pilot_root / "traces"
    if not traces_root.exists():
        print(f"No traces at {traces_root}", file=sys.stderr)
        return 1

    dirs = sorted(p for p in traces_root.iterdir() if p.is_dir())
    if args.limit > 0:
        dirs = dirs[: args.limit]

    report: dict = {
        "n": len(dirs),
        "failures": [],
        "ground_truth_failures": 0,
        "pipeline_eligible": 0,
        "intentionally_incomplete": 0,
        "strict_fault_observables": bool(args.strict_fault_observables),
        "results": [],
    }

    for tdir in dirs:
        item_result = _validate_dir(
            tdir,
            args.pilot_root,
            strict_fault_observables=args.strict_fault_observables,
        )
        pipeline = {}
        warnings = list(item_result.warnings)
        if item_result.incomplete:
            report["intentionally_incomplete"] += 1

        if args.pipeline and item_result.suitable_for_dag_attribution and not item_result.incomplete:
            events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
            arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
            pt = ProvenanceTrace()
            pt.load_records(events, arts)
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
            report["pipeline_eligible"] += 1
            if not pipeline["fingerprint_unchanged"]:
                item_result.errors.append("pipeline mutated provenance fingerprint")
                item_result.ok = False
        elif args.pipeline:
            warnings.append("skipped RPA/MFAV (incomplete or unsuitable DAG)")

        entry = {
            "trace_id": tdir.name,
            "ok": item_result.ok,
            "errors": item_result.errors,
            "warnings": warnings,
            "incomplete": item_result.incomplete,
            "ground_truth_failures": item_result.ground_truth_failures,
            "pipeline": pipeline,
        }
        report["results"].append(entry)
        report["ground_truth_failures"] += item_result.ground_truth_failures
        if not item_result.ok:
            report["failures"].append(entry)

    out = args.pilot_root / "validation_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"checked={len(dirs)} failures={len(report['failures'])} "
        f"gt_error_total={report['ground_truth_failures']} "
        f"incomplete={report['intentionally_incomplete']} "
        f"pipeline_eligible={report['pipeline_eligible']} report={out}"
    )
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
