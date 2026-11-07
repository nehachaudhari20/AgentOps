#!/usr/bin/env python3
"""
AgentTrust staged reproducibility runner (Phase 2.12 + 2.13 correction).

A skipped mandatory evaluation stage MUST NOT be reported as a fully successful
complete reproduction. Exit codes distinguish complete / partial / smoke / failed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.repro.manifest import build_run_manifest, utc_now, write_manifest

STAGES = (
    "env",
    "dataset_validate",
    "dataset_regenerate",
    "pipeline",
    "baselines",
    "stats",
    "full_evaluation",
    "repeatability",
    "tests",
    "validators",
    "phase_2_13",
)

# Stages that may not silently skip required artifacts
MANDATORY_WHEN_REQUESTED = frozenset(
    {"stats", "full_evaluation", "tests", "validators", "phase_2_13", "repeatability"}
)


class StageResult:
    def __init__(self, code: int, *, status: str, detail: str = ""):
        self.code = code
        self.status = status  # ok | failed | skipped_mandatory | smoke
        self.detail = detail


def _run(cmd: list[str], *, cwd: Path = ROOT) -> int:
    print(f"+ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(cwd))


def stage_env() -> StageResult:
    code = _run(
        [
            sys.executable,
            "-c",
            "from agenttrust import ProvenanceTrace, ConservedRPA, MFAV, AgentTrustPipeline, PLHC",
        ]
    )
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_dataset_validate() -> StageResult:
    code = _run(
        [
            sys.executable,
            "experiments/scripts/validate_experimental_dataset.py",
            "--root",
            "data/benchmarks/experimental_2_9",
            "--max-trace-checks",
            "20",
        ]
    )
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_dataset_regenerate() -> StageResult:
    print("dataset_regenerate: explicit regeneration requested")
    code = _run(
        [
            sys.executable,
            "experiments/scripts/generate_experimental_dataset.py",
            "--root",
            "data/benchmarks/experimental_2_9",
            "--limit",
            "2",
        ]
    )
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_pipeline() -> StageResult:
    pilot = ROOT / "data" / "benchmarks" / "pilot" / "traces"
    dirs = sorted(p for p in pilot.iterdir() if p.is_dir()) if pilot.is_dir() else []
    if not dirs:
        return StageResult(1, status="failed", detail="no pilot traces")
    out = ROOT / "experiments" / "results" / "repro_scratch" / "pipeline_smoke"
    out.mkdir(parents=True, exist_ok=True)
    code = _run(
        [
            sys.executable,
            "experiments/scripts/evaluate_agenttrust.py",
            "--trace",
            str(dirs[0]),
            "--out",
            str(out),
            "--validate-only",
            "--primary-outcome-only",
        ]
    )
    return StageResult(code, status="smoke" if code == 0 else "failed", detail="pipeline_smoke")


def stage_baselines() -> StageResult:
    out = ROOT / "experiments" / "results" / "repro_scratch" / "baselines_smoke"
    out.mkdir(parents=True, exist_ok=True)
    code = _run(
        [
            sys.executable,
            "experiments/scripts/run_baseline_comparison.py",
            "--split",
            "development",
            "--limit",
            "3",
            "--out",
            str(out),
            "--plhc-sample",
            "2",
        ]
    )
    return StageResult(code, status="smoke" if code == 0 else "failed")


def stage_stats(*, allow_smoke_skip: bool = False) -> StageResult:
    """
    Stats stage requires frozen comparison artifacts OR recomputation.

    Phase 2.13: missing mandatory artifacts → non-zero unless --smoke.
    """
    out = ROOT / "experiments" / "results" / "repro_scratch" / "stats_smoke"
    out.mkdir(parents=True, exist_ok=True)
    held = ROOT / "experiments" / "results" / "phase_2_10" / "heldout_test_comparison.json"
    preserved = ROOT / "experiments" / "results" / "phase_2_13" / "final_rq_master.json"
    if not held.is_file() and not preserved.is_file():
        msg = (
            "stats: mandatory frozen comparison/evaluation artifacts missing "
            "(experiments/results/phase_2_10 or phase_2_13). "
            "Run full_evaluation or restore preserved results."
        )
        print(msg, file=sys.stderr)
        if allow_smoke_skip:
            print("stats: --smoke allows skip → partial reproduction", flush=True)
            return StageResult(0, status="skipped_mandatory", detail=msg)
        return StageResult(3, status="skipped_mandatory", detail=msg)

    code = _run(
        [
            sys.executable,
            "experiments/scripts/run_final_evaluation.py",
            "--skip-rerun-comparison",
            "--splits",
            "development",
            "--limit",
            "5",
            "--rq4-limit",
            "5",
            "--rq5-limit",
            "3",
            "--out",
            str(out),
        ]
    )
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_full_evaluation() -> StageResult:
    out = ROOT / "experiments" / "results" / "phase_2_13"
    out.mkdir(parents=True, exist_ok=True)
    code = _run(
        [
            sys.executable,
            "experiments/scripts/run_final_evaluation.py",
            "--out",
            str(out),
            "--comparison-root",
            str(out / "comparisons"),
        ]
    )
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_repeatability() -> StageResult:
    code = _run([sys.executable, "experiments/scripts/check_repeatability.py"])
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_tests() -> StageResult:
    code = _run([sys.executable, "-m", "pytest", "tests", "-q"])
    return StageResult(code, status="ok" if code == 0 else "failed")


def stage_validators() -> StageResult:
    cmds = [
        [sys.executable, "experiments/scripts/validate_benchmark_pilot.py", "--pipeline"],
        [sys.executable, "experiments/scripts/validate_phase25_fault_matrix.py"],
        [sys.executable, "experiments/scripts/validate_plhc.py"],
        [sys.executable, "experiments/scripts/evaluate_assurance_profiles.py"],
        [sys.executable, "experiments/scripts/validate_experimental_dataset.py"],
    ]
    for c in cmds:
        code = _run(c)
        if code != 0:
            return StageResult(code, status="failed", detail=" ".join(c))
    return StageResult(0, status="ok")


def stage_phase_2_13() -> StageResult:
    code = _run([sys.executable, "experiments/scripts/validate_phase_2_13.py"])
    return StageResult(code, status="ok" if code == 0 else "failed")


HANDLERS = {
    "env": stage_env,
    "dataset_validate": stage_dataset_validate,
    "dataset_regenerate": stage_dataset_regenerate,
    "pipeline": stage_pipeline,
    "baselines": stage_baselines,
    "stats": stage_stats,
    "full_evaluation": stage_full_evaluation,
    "repeatability": stage_repeatability,
    "tests": stage_tests,
    "validators": stage_validators,
    "phase_2_13": stage_phase_2_13,
}


def _classify_reproduction(results: dict[str, StageResult]) -> str:
    if any(r.status == "failed" or r.code != 0 for r in results.values()):
        # Distinguish skipped_mandatory non-zero
        if any(r.status == "skipped_mandatory" and r.code != 0 for r in results.values()):
            return "partial_reproduction_missing_artifacts"
        return "failed_reproduction"
    if any(r.status == "skipped_mandatory" for r in results.values()):
        return "partial_reproduction"
    if any(r.status == "smoke" for r in results.values()) and not any(
        s in results for s in ("full_evaluation", "phase_2_13")
    ):
        return "smoke_test"
    if "full_evaluation" in results or "phase_2_13" in results:
        return "complete_reproduction"
    return "partial_reproduction"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", action="append", choices=list(STAGES))
    p.add_argument(
        "--all-safe",
        action="store_true",
        help="Non-destructive stages including phase_2_13 validator (not full corpus eval)",
    )
    p.add_argument(
        "--complete",
        action="store_true",
        help="Complete reproduction including full_evaluation + phase_2_13",
    )
    p.add_argument("--regenerate-dataset", action="store_true")
    p.add_argument("--force-results", action="store_true")
    p.add_argument(
        "--smoke",
        action="store_true",
        help="Allow stats stage to soft-skip missing frozen artifacts (exit still marks partial)",
    )
    p.add_argument(
        "--manifest-out",
        type=Path,
        default=ROOT / "experiments" / "results" / "repro_scratch" / "run_manifest.json",
    )
    args = p.parse_args(argv)

    if args.complete:
        stages = [
            "env",
            "dataset_validate",
            "pipeline",
            "baselines",
            "full_evaluation",
            "repeatability",
            "tests",
            "validators",
            "phase_2_13",
        ]
    elif args.all_safe:
        stages = [
            "env",
            "dataset_validate",
            "pipeline",
            "baselines",
            "stats",
            "repeatability",
            "tests",
            "validators",
            "phase_2_13",
        ]
    elif args.stage:
        stages = args.stage
    else:
        stages = ["env", "dataset_validate", "repeatability", "tests", "phase_2_13"]

    if "dataset_regenerate" in stages and not args.regenerate_dataset:
        print("Refusing dataset_regenerate without --regenerate-dataset", file=sys.stderr)
        return 2
    if args.force_results:
        print("note: --force-results acknowledged; default stages write to versioned paths")

    started = utc_now()
    results: dict[str, StageResult] = {}
    overall = 0
    for st in stages:
        print(f"\n=== STAGE {st} ===", flush=True)
        if st == "stats":
            res = stage_stats(allow_smoke_skip=args.smoke)
        else:
            res = HANDLERS[st]()
        results[st] = res
        if res.code != 0:
            overall = res.code
            print(f"STAGE FAIL {st} exit={res.code} status={res.status}", flush=True)
            break
        print(f"STAGE OK {st} status={res.status}", flush=True)

    ended = utc_now()
    classification = _classify_reproduction(results)
    # Complete reproduction cannot claim success if mandatory skipped
    if classification in (
        "partial_reproduction_missing_artifacts",
        "failed_reproduction",
    ):
        overall = overall or 3
    if classification == "partial_reproduction" and any(
        r.status == "skipped_mandatory" for r in results.values()
    ):
        # Soft-skip under --smoke: non-zero to avoid false complete success
        if overall == 0:
            overall = 4  # partial
            print(
                "REPRODUCTION CLASSIFIED PARTIAL (mandatory skip under --smoke); exit=4",
                flush=True,
            )

    fp = None
    fp_path = ROOT / "data" / "benchmarks" / "experimental_2_9" / "design_fingerprint.json"
    if fp_path.is_file():
        fp = json.loads(fp_path.read_text(encoding="utf-8")).get("design_fingerprint_sha256")

    stage_codes = {k: {"exit": v.code, "status": v.status, "detail": v.detail} for k, v in results.items()}
    man = build_run_manifest(
        run_id=f"repro-{started}",
        stage="+".join(stages),
        commands=[f"python experiments/scripts/reproduce.py --stage {s}" for s in stages],
        output_paths=[str(args.manifest_out.as_posix())],
        dataset_fingerprint=fp,
        validation_status=classification if overall == 0 else f"failed:{classification}",
        notes=[f"stage_results={stage_codes}", f"classification={classification}"],
        started_at=started,
        ended_at=ended,
    )
    write_manifest(args.manifest_out, man)
    summary = {
        "overall_exit": overall,
        "classification": classification,
        "stages": stage_codes,
        "manifest": str(args.manifest_out),
    }
    print(json.dumps(summary, indent=2))
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
