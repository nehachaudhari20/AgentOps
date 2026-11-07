#!/usr/bin/env python3
"""
AgentTrust staged reproducibility runner (Phase 2.12).

Stages are explicit; each stage logs success/failure and returns a meaningful exit code.
Does NOT overwrite frozen result directories unless --force-results is passed.
Does NOT regenerate datasets unless --regenerate-dataset is passed.
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
    "repeatability",
    "tests",
    "validators",
)


def _run(cmd: list[str], *, cwd: Path = ROOT) -> int:
    print(f"+ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(cwd))


def stage_env() -> int:
    code = _run([sys.executable, "-c", "from agenttrust import ProvenanceTrace, ConservedRPA, MFAV, AgentTrustPipeline, PLHC"])
    if code != 0:
        return code
    print("env: imports ok")
    return 0


def stage_dataset_validate() -> int:
    return _run(
        [
            sys.executable,
            "experiments/scripts/validate_experimental_dataset.py",
            "--root",
            "data/benchmarks/experimental_2_9",
            "--max-trace-checks",
            "20",
        ]
    )


def stage_dataset_regenerate() -> int:
    print("dataset_regenerate: explicit regeneration requested")
    return _run(
        [
            sys.executable,
            "experiments/scripts/generate_experimental_dataset.py",
            "--root",
            "data/benchmarks/experimental_2_9",
            "--limit",
            "2",
        ]
    )


def stage_pipeline() -> int:
    # Single pilot trace smoke — does not overwrite frozen experimental results
    pilot = ROOT / "data" / "benchmarks" / "pilot" / "traces"
    dirs = sorted(p for p in pilot.iterdir() if p.is_dir()) if pilot.is_dir() else []
    if not dirs:
        print("pipeline: no pilot traces", file=sys.stderr)
        return 1
    out = ROOT / "experiments" / "results" / "repro_scratch" / "pipeline_smoke"
    out.mkdir(parents=True, exist_ok=True)
    return _run(
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


def stage_baselines() -> int:
    out = ROOT / "experiments" / "results" / "repro_scratch" / "baselines_smoke"
    out.mkdir(parents=True, exist_ok=True)
    return _run(
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


def stage_stats() -> int:
    out = ROOT / "experiments" / "results" / "repro_scratch" / "stats_smoke"
    out.mkdir(parents=True, exist_ok=True)
    # Recompute RQ aggregates from existing comparison if present; else skip with note
    held = ROOT / "experiments" / "results" / "phase_2_10" / "heldout_test_comparison.json"
    if not held.is_file():
        print("stats: frozen comparison missing under experiments/results/phase_2_10 (gitignored); smoke skip")
        return 0
    return _run(
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


def stage_repeatability() -> int:
    return _run([sys.executable, "experiments/scripts/check_repeatability.py"])


def stage_tests() -> int:
    return _run([sys.executable, "-m", "pytest", "tests", "-q"])


def stage_validators() -> int:
    cmds = [
        [sys.executable, "experiments/scripts/validate_benchmark_pilot.py", "--pipeline"],
        [sys.executable, "experiments/scripts/validate_phase25_fault_matrix.py"],
        [sys.executable, "experiments/scripts/validate_plhc.py"],
        [sys.executable, "experiments/scripts/evaluate_assurance_profiles.py"],
    ]
    for c in cmds:
        code = _run(c)
        if code != 0:
            return code
    return 0


HANDLERS = {
    "env": stage_env,
    "dataset_validate": stage_dataset_validate,
    "dataset_regenerate": stage_dataset_regenerate,
    "pipeline": stage_pipeline,
    "baselines": stage_baselines,
    "stats": stage_stats,
    "repeatability": stage_repeatability,
    "tests": stage_tests,
    "validators": stage_validators,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--stage",
        action="append",
        choices=list(STAGES),
        help="Stage to run (repeatable). Default: env,dataset_validate,repeatability,tests",
    )
    p.add_argument(
        "--all-safe",
        action="store_true",
        help="Run non-destructive stages: env, dataset_validate, pipeline, baselines, stats, repeatability, tests, validators",
    )
    p.add_argument(
        "--regenerate-dataset",
        action="store_true",
        help="Allow dataset_regenerate stage (destructive/additive generation)",
    )
    p.add_argument(
        "--force-results",
        action="store_true",
        help="Reserved: acknowledge overwriting frozen results (not used by default paths)",
    )
    p.add_argument(
        "--manifest-out",
        type=Path,
        default=ROOT / "experiments" / "results" / "repro_scratch" / "run_manifest.json",
    )
    args = p.parse_args(argv)

    if args.all_safe:
        stages = [
            "env",
            "dataset_validate",
            "pipeline",
            "baselines",
            "stats",
            "repeatability",
            "tests",
            "validators",
        ]
    elif args.stage:
        stages = args.stage
    else:
        stages = ["env", "dataset_validate", "repeatability", "tests"]

    if "dataset_regenerate" in stages and not args.regenerate_dataset:
        print("Refusing dataset_regenerate without --regenerate-dataset", file=sys.stderr)
        return 2
    if args.force_results:
        print("note: --force-results acknowledged; default stages still write to repro_scratch/")

    started = utc_now()
    results = {}
    overall = 0
    for st in stages:
        print(f"\n=== STAGE {st} ===", flush=True)
        code = HANDLERS[st]()
        results[st] = code
        if code != 0:
            overall = code
            print(f"STAGE FAIL {st} exit={code}", flush=True)
            break
        print(f"STAGE OK {st}", flush=True)

    ended = utc_now()
    fp = None
    fp_path = ROOT / "data" / "benchmarks" / "experimental_2_9" / "design_fingerprint.json"
    if fp_path.is_file():
        fp = json.loads(fp_path.read_text(encoding="utf-8")).get("design_fingerprint_sha256")

    man = build_run_manifest(
        run_id=f"repro-{started}",
        stage="+".join(stages),
        commands=[f"python experiments/scripts/reproduce.py --stage {s}" for s in stages],
        output_paths=[str(args.manifest_out.as_posix())],
        dataset_fingerprint=fp,
        validation_status="ok" if overall == 0 else "failed",
        notes=[f"stage_exit_codes={results}"],
        started_at=started,
        ended_at=ended,
    )
    write_manifest(args.manifest_out, man)
    print(json.dumps({"overall_exit": overall, "stages": results, "manifest": str(args.manifest_out)}, indent=2))
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
