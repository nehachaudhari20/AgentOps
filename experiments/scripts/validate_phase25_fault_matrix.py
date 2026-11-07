#!/usr/bin/env python3
"""
Strict Phase 2.5 fault-matrix validation on *freshly generated* traces.

Does NOT overwrite data/benchmarks/pilot/. Writes under data/benchmarks/phase25_fault_matrix/
(ephemeral validation corpus for generator 2.5.x semantics).

Validation modes (documented):
  A. Historical pilot: experiments/scripts/validate_benchmark_pilot.py [--pipeline]
     → package/schema/GT/pipeline; does NOT claim Phase 2.5 fault-observable semantics.
  B. This script: fresh 2.5 generator + check_fault_observables=True for every fault type.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark import (
    GENERATOR_VERSION,
    BenchmarkConfig,
    BenchmarkGenerator,
    FaultType,
    ScenarioId,
    ScaleTier,
    TopologyId,
    validate_generated_trace,
)


def require_matching_generator_version(actual: str, expected: str = GENERATOR_VERSION) -> None:
    """
    Hard-fail before any generation/validation when versions differ.

    Raises SystemExit with code 2 (does not mutate prior Phase 2.5.1 reports).
    """
    if actual != expected:
        print(
            f"ERROR: generator version mismatch: expected={expected!r} actual={actual!r}. "
            "Refusing to generate or validate the Phase 2.5 fault matrix.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def fault_matrix_configs() -> list[BenchmarkConfig]:
    """One S1 trace per fault type (+ dedicated delegation modes via topology choice)."""
    configs: list[BenchmarkConfig] = []
    scenarios = list(ScenarioId)
    for i, fault in enumerate(FaultType):
        # MIXED yields INVOKES for callee_failed; SEQUENTIAL covers missing_callee when no invokes
        topo = TopologyId.MIXED if fault == FaultType.DELEGATION_FAILURE else TopologyId.SEQUENTIAL
        # Second delegation sample on sequential forces missing_callee path
        configs.append(
            BenchmarkConfig(
                scenario_id=scenarios[i % len(scenarios)],
                topology_id=topo,
                scale_tier=ScaleTier.S1,
                seed=2500 + i,
                fault_types=(fault.value,),
                incomplete=(fault == FaultType.INCOMPLETE_TRACE),
            )
        )
    # Explicit missing-callee sample
    configs.append(
        BenchmarkConfig(
            scenario_id=ScenarioId.FINANCIAL_LOAN,
            topology_id=TopologyId.SEQUENTIAL,
            scale_tier=ScaleTier.S1,
            seed=2599,
            fault_types=(FaultType.DELEGATION_FAILURE.value,),
            incomplete=False,
        )
    )
    return configs


def main() -> int:
    out_root = ROOT / "data" / "benchmarks" / "phase25_fault_matrix"
    traces_dir = out_root / "traces"
    gt_dir = out_root / "ground_truth"
    man_dir = out_root / "manifests"
    traces_dir.mkdir(parents=True, exist_ok=True)

    gen = BenchmarkGenerator()
    require_matching_generator_version(gen.generator_version, GENERATOR_VERSION)

    configs = fault_matrix_configs()
    report: dict = {
        "generator_version": gen.generator_version,
        "expected_generator_version": GENERATOR_VERSION,
        "mode": "phase_2_5_strict_fault_observables",
        "n_configs": len(configs),
        "fault_types_exercised": [],
        "failures": [],
        "leakage_violations": 0,
        "results": [],
        "notes": [
            "Historical pilot is validated separately without claiming 2.5 fault semantics.",
            "This corpus is for strict generator validation only.",
            "Generator version mismatch exits before generation (exit code 2).",
        ],
    }

    fault_seen: set[str] = set()
    for cfg in configs:
        pkg = gen.generate(cfg)
        gen.write_trace(pkg, events_dir=traces_dir, ground_truth_dir=gt_dir, manifests_dir=man_dir)
        v = validate_generated_trace(
            pkg,
            require_complete=False,
            load_provenance=True,
            verify_fingerprint=True,
            check_fault_observables=True,
        )
        for ft in pkg.manifest.fault_types:
            fault_seen.add(ft)
        leakage = [e for e in v.errors if "answer-revealing" in e or "prohibited" in e or "leaked" in e]
        report["leakage_violations"] += len(leakage)
        entry = {
            "trace_id": pkg.manifest.trace_id,
            "fault_types": pkg.manifest.fault_types,
            "ok": v.ok,
            "errors": v.errors,
            "incomplete": v.incomplete,
            "intervention_count": pkg.manifest.intervention_count,
            "leakage_errors": leakage,
        }
        report["results"].append(entry)
        if not v.ok:
            report["failures"].append(entry)

    report["fault_types_exercised"] = sorted(fault_seen)
    report["n_fault_types_exercised"] = len(fault_seen)
    report["n_failures"] = len(report["failures"])
    report["n_checked"] = len(configs)

    summary_path = out_root / "strict_validation_report.json"
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"checked={report['n_checked']} failures={report['n_failures']} "
        f"fault_types={report['n_fault_types_exercised']} "
        f"leakage_violations={report['leakage_violations']} "
        f"report={summary_path}"
    )
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
