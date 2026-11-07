#!/usr/bin/env python3
"""
Run Assurance Profiles over historical pilot and Phase 2.5.1 fault-matrix traces.

Fail-closed: any per-trace evaluation error → non-zero exit after writing diagnostics.
Does not use ground truth to compute profile values.
Does not silently skip unsupported traces.
"""

from __future__ import annotations

import hashlib
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
    PLHC,
    ProvenanceTrace,
)
from agenttrust.assurance.models import ASSURANCE_ALGORITHM_VERSION
from agenttrust.attribution.rpa import RPAConfig, RPAError
from agenttrust.benchmark import GENERATOR_VERSION
from agenttrust.mlpg.projections import ProjectionKind

COMMAND = "python experiments/scripts/evaluate_assurance_profiles.py"


def _corpus_fingerprint(traces_root: Path) -> str:
    if not traces_root.exists():
        return ""
    h = hashlib.sha256()
    for tdir in sorted(p for p in traces_root.iterdir() if p.is_dir()):
        h.update(tdir.name.encode("utf-8"))
        for name in ("events.json", "artifacts.json"):
            f = tdir / name
            if f.exists():
                h.update(f.read_bytes())
    return h.hexdigest()


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
    report: dict = {
        "corpus": label,
        "traces_root": str(traces_root.as_posix()),
        "corpus_readable": traces_root.exists() and traces_root.is_dir(),
        "corpus_fingerprint_sha256": _corpus_fingerprint(traces_root) if traces_root.exists() else None,
        "n_examined": 0,
        "n_profiles_ok": 0,
        "n_incomplete_overall": 0,
        "n_contradicted_overall": 0,
        "n_errors": 0,
        "dimension_status_counts": {},
        "unavailable_dimensions": {},
        "invalid_or_error": [],
        "profiles": [],
        "assurance_algorithm_version": ASSURANCE_ALGORITHM_VERSION,
        "notes": [
            "Ground truth not used to compute Assurance Profile values.",
            "GT used only for optional planted-incompleteness annotation.",
            "Fail-closed: any trace error increments n_errors and forces non-zero exit.",
        ],
    }

    if not traces_root.exists() or not traces_root.is_dir():
        report["invalid_or_error"].append(
            {
                "trace_id": None,
                "error": f"corpus directory missing or unreadable: {traces_root}",
            }
        )
        report["n_errors"] += 1
        return report

    dirs = sorted(p for p in traces_root.iterdir() if p.is_dir())
    report["n_examined"] = len(dirs)
    if not dirs:
        report["invalid_or_error"].append(
            {"trace_id": None, "error": f"corpus has zero trace directories: {traces_root}"}
        )
        report["n_errors"] += 1
        return report

    for tdir in dirs:
        entry: dict = {"trace_id": tdir.name, "ok": False}
        try:
            events, arts, gt = _load_trace_package(tdir, gt_dir=gt_dir)
            pt = ProvenanceTrace()
            pt.load_records(events, arts)
            planted_incomplete = bool(
                gt and (gt.get("quality") or {}).get("intentionally_incomplete")
            )
            entry["planted_incomplete_gt_annotation"] = planted_incomplete
            entry["provenance_fingerprint"] = pt.fingerprint()

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

            # PLHC: build snapshot + genesis checkpoint, verify round-trip (fail-closed on mismatch)
            plhc = PLHC()
            snap = plhc.build_snapshot(pt)
            cp = plhc.create_checkpoint(snap, sequence_number=0)
            plhc_result = plhc.verify_against_checkpoint(pt, cp)
            entry["plhc_status"] = plhc_result.status.value
            entry["plhc_merkle_root"] = snap.merkle_root
            entry["plhc_leaf_count"] = snap.leaf_count
            if plhc_result.status.value != "verified":
                raise RuntimeError(
                    f"PLHC round-trip failed: {plhc_result.status.value}: {plhc_result.explanation}"
                )

            profile = calc.compute(
                pt,
                rpa_result=rpa,
                mfav_result=mfav,
                mfav_p1=mfav_p1,
                mfav_p2=mfav_p2,
                plhc_result=plhc_result,
            )
            entry["ok"] = True
            entry["overall_status"] = profile.overall_status.value
            entry["dimension_statuses"] = {
                k: v.status.value for k, v in profile.dimensions.items()
            }
            report["n_profiles_ok"] += 1
            if profile.overall_status.value == "incomplete":
                report["n_incomplete_overall"] += 1
            if profile.overall_status.value == "contradicted":
                report["n_contradicted_overall"] += 1
            for did, d in profile.dimensions.items():
                dsc = report["dimension_status_counts"].setdefault(did, {})
                dsc[d.status.value] = dsc.get(d.status.value, 0) + 1
                if d.status.value == "unavailable":
                    report["unavailable_dimensions"][did] = (
                        report["unavailable_dimensions"].get(did, 0) + 1
                    )
        except Exception as exc:
            report["n_errors"] += 1
            entry["error"] = str(exc)
            report["invalid_or_error"].append(entry)
        report["profiles"].append(entry)
        # Every trace must appear in profiles (ok or error)
        assert entry["trace_id"] == tdir.name

    return report


def main() -> int:
    out = ROOT / "experiments" / "results" / "assurance_phase26"
    out.mkdir(parents=True, exist_ok=True)

    pilot_traces = ROOT / "data" / "benchmarks" / "pilot" / "traces"
    pilot_gt = ROOT / "data" / "benchmarks" / "pilot" / "ground_truth"
    matrix_traces = ROOT / "data" / "benchmarks" / "phase25_fault_matrix" / "traces"
    matrix_gt = ROOT / "data" / "benchmarks" / "phase25_fault_matrix" / "ground_truth"

    pilot_report = _evaluate_dir(pilot_traces, pilot_gt, "historical_pilot_2.4.0")
    matrix_report = _evaluate_dir(matrix_traces, matrix_gt, "phase25_fault_matrix")

    summary = {
        "command": COMMAND,
        "assurance_algorithm_version": ASSURANCE_ALGORITHM_VERSION,
        "benchmark_generator_version_constant": GENERATOR_VERSION,
        "pilot": {
            "n_examined": pilot_report["n_examined"],
            "n_profiles_ok": pilot_report["n_profiles_ok"],
            "n_incomplete_overall": pilot_report["n_incomplete_overall"],
            "n_contradicted_overall": pilot_report["n_contradicted_overall"],
            "n_errors": pilot_report["n_errors"],
            "unavailable_dimensions": pilot_report["unavailable_dimensions"],
            "dimension_status_counts": pilot_report["dimension_status_counts"],
            "corpus_fingerprint_sha256": pilot_report["corpus_fingerprint_sha256"],
            "corpus_readable": pilot_report["corpus_readable"],
        },
        "fault_matrix": {
            "n_examined": matrix_report["n_examined"],
            "n_profiles_ok": matrix_report["n_profiles_ok"],
            "n_incomplete_overall": matrix_report["n_incomplete_overall"],
            "n_contradicted_overall": matrix_report["n_contradicted_overall"],
            "n_errors": matrix_report["n_errors"],
            "unavailable_dimensions": matrix_report["unavailable_dimensions"],
            "dimension_status_counts": matrix_report["dimension_status_counts"],
            "corpus_fingerprint_sha256": matrix_report["corpus_fingerprint_sha256"],
            "corpus_readable": matrix_report["corpus_readable"],
        },
        "error_records": {
            "pilot": pilot_report["invalid_or_error"],
            "fault_matrix": matrix_report["invalid_or_error"],
        },
    }

    # Compact per-trace outcomes (status only — not full profile dumps)
    compact = {
        "pilot_traces": [
            {
                "trace_id": p["trace_id"],
                "ok": p.get("ok"),
                "overall_status": p.get("overall_status"),
                "error": p.get("error"),
                "dimension_statuses": p.get("dimension_statuses"),
            }
            for p in pilot_report["profiles"]
        ],
        "fault_matrix_traces": [
            {
                "trace_id": p["trace_id"],
                "ok": p.get("ok"),
                "overall_status": p.get("overall_status"),
                "error": p.get("error"),
                "dimension_statuses": p.get("dimension_statuses"),
            }
            for p in matrix_report["profiles"]
        ],
    }

    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "per_trace_status.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "pilot_diagnostics.json").write_text(
        json.dumps(pilot_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "fault_matrix_diagnostics.json").write_text(
        json.dumps(matrix_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, sort_keys=True))

    total_errors = pilot_report["n_errors"] + matrix_report["n_errors"]
    if total_errors > 0:
        print(f"FAIL-CLOSED: {total_errors} trace/corpus evaluation error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
