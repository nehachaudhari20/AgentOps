#!/usr/bin/env python3
"""
Run Assurance Profiles over historical pilot and Phase 2.5.1 fault-matrix traces.

Keeps results separate. Does not use ground truth to compute profile values.
Ground truth is used only to annotate planted incompleteness for reporting.
Does not silently skip unsupported traces — records errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust import (
    AssuranceProfileCalculator,
    ConservedRPA,
    MFAV,
    ProvenanceTrace,
)
from agenttrust.assurance.report import write_profiles_json
from agenttrust.attribution.rpa import RPAConfig, RPAError
from agenttrust.mlpg.projections import ProjectionKind


def _load_trace_package(tdir: Path, *, gt_dir: Path | None = None) -> tuple[list, list, dict | None]:
    events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    gt = None
    if gt_dir is not None:
        gpath = gt_dir / f"{tdir.name}.json"
        if gpath.exists():
            gt = json.loads(gpath.read_text(encoding="utf-8"))
    return events, arts, gt


def _evaluate_dir(traces_root: Path, gt_dir: Path | None, label: str) -> dict:
    calc = AssuranceProfileCalculator()
    dirs = sorted(p for p in traces_root.iterdir() if p.is_dir()) if traces_root.exists() else []
    report = {
        "corpus": label,
        "n_examined": len(dirs),
        "n_profiles_ok": 0,
        "n_incomplete_overall": 0,
        "n_errors": 0,
        "unavailable_dimensions": {},
        "invalid_or_error": [],
        "profiles": [],
        "notes": [
            "Ground truth not used to compute Assurance Profile values.",
            "GT used only for optional planted-incompleteness annotation.",
        ],
    }
    profile_objs = []

    for tdir in dirs:
        entry = {"trace_id": tdir.name, "ok": False}
        try:
            events, arts, gt = _load_trace_package(tdir, gt_dir=gt_dir)
            pt = ProvenanceTrace()
            pt.load_records(events, arts)
            planted_incomplete = bool(
                gt
                and (gt.get("quality") or {}).get("intentionally_incomplete")
            )
            entry["planted_incomplete_gt_annotation"] = planted_incomplete

            rpa = None
            mfav = None
            mfav_p1 = None
            mfav_p2 = None
            try:
                results = ConservedRPA().allocate_from_trace(
                    pt, projection_kind=ProjectionKind.P1_DIRECT
                )
                rpa = results[0]
                mfav = MFAV().compute(rpa, trace=pt)
                # P2 companion for sensitivity when possible
                try:
                    r2 = ConservedRPA().allocate_from_trace(
                        pt, projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE
                    )[0]
                    mfav_p2 = MFAV().compute(r2, trace=pt)
                    mfav_p1 = mfav
                except RPAError as exc:
                    entry["p2_error"] = str(exc)
            except RPAError as exc:
                entry["rpa_error"] = str(exc)
                # Retry with allow_incomplete for incomplete traces (still recorded as incomplete)
                if pt.completeness().incomplete:
                    try:
                        results = ConservedRPA().allocate_from_trace(
                            pt,
                            projection_kind=ProjectionKind.P1_DIRECT,
                            config=RPAConfig(allow_incomplete=True),
                        )
                        rpa = results[0]
                        mfav = MFAV().compute(rpa, trace=pt)
                        entry["rpa_override"] = "allow_incomplete"
                    except Exception as exc2:
                        entry["rpa_override_error"] = str(exc2)

            profile = calc.compute(
                pt,
                rpa_result=rpa,
                mfav_result=mfav,
                mfav_p1=mfav_p1,
                mfav_p2=mfav_p2,
            )
            entry["ok"] = True
            entry["overall_status"] = profile.overall_status.value
            entry["dimension_statuses"] = {
                k: v.status.value for k, v in profile.dimensions.items()
            }
            report["n_profiles_ok"] += 1
            if profile.overall_status.value == "incomplete":
                report["n_incomplete_overall"] += 1
            for did, d in profile.dimensions.items():
                if d.status.value == "unavailable":
                    report["unavailable_dimensions"][did] = (
                        report["unavailable_dimensions"].get(did, 0) + 1
                    )
            profile_objs.append(profile)
        except Exception as exc:
            report["n_errors"] += 1
            entry["error"] = str(exc)
            report["invalid_or_error"].append(entry)
        report["profiles"].append(entry)

    return report, profile_objs


def main() -> int:
    out = ROOT / "experiments" / "results" / "assurance_phase26"
    out.mkdir(parents=True, exist_ok=True)

    pilot_traces = ROOT / "data" / "benchmarks" / "pilot" / "traces"
    pilot_gt = ROOT / "data" / "benchmarks" / "pilot" / "ground_truth"
    matrix_traces = ROOT / "data" / "benchmarks" / "phase25_fault_matrix" / "traces"
    matrix_gt = ROOT / "data" / "benchmarks" / "phase25_fault_matrix" / "ground_truth"

    pilot_report, pilot_profiles = _evaluate_dir(pilot_traces, pilot_gt, "historical_pilot_2.4.0")
    matrix_report, matrix_profiles = _evaluate_dir(
        matrix_traces, matrix_gt, "phase25_fault_matrix"
    )

    write_profiles_json(out / "pilot_profiles.json", pilot_profiles, extra=pilot_report)
    write_profiles_json(out / "fault_matrix_profiles.json", matrix_profiles, extra=matrix_report)

    summary = {
        "pilot": {
            "n_examined": pilot_report["n_examined"],
            "n_profiles_ok": pilot_report["n_profiles_ok"],
            "n_incomplete_overall": pilot_report["n_incomplete_overall"],
            "n_errors": pilot_report["n_errors"],
            "unavailable_dimensions": pilot_report["unavailable_dimensions"],
        },
        "fault_matrix": {
            "n_examined": matrix_report["n_examined"],
            "n_profiles_ok": matrix_report["n_profiles_ok"],
            "n_incomplete_overall": matrix_report["n_incomplete_overall"],
            "n_errors": matrix_report["n_errors"],
            "unavailable_dimensions": matrix_report["unavailable_dimensions"],
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    # Non-zero only if hard evaluation errors occurred with zero successful profiles when traces exist
    if pilot_traces.exists() and pilot_report["n_examined"] and pilot_report["n_profiles_ok"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
