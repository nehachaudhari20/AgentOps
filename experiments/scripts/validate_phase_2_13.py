#!/usr/bin/env python3
"""
Phase 2.13 research-validity validator.

Checks paired power module, bridge corpus expectations, sampling determinism,
attribution alignment disclosure, and reproduction failure semantics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark.bridge_scenarios import (
    ALL_SCENARIO_BUILDERS,
    analyze_projection_diff,
    generate_bridge_corpus,
)
from agenttrust.benchmark.dataset.attribution_reference import ALIGNMENT_DISCLOSURE
from agenttrust.benchmark.dataset.power import power_report, simulate_paired_power
from agenttrust.evaluation.sampling import stratified_sample_entries


def main() -> int:
    errors: list[str] = []

    # 1) Paired power
    try:
        sim = simulate_paired_power(
            n_pairs=72,
            p_both=0.35,
            p_fault_only=0.21,
            p_clean_only=0.09,
            n_sims=2000,
            seed=42,
        )
        report = power_report(n_sims=500)
        if report["report_version"] != "2.13.0":
            errors.append("power report_version != 2.13.0")
        if "INVALID" not in report.get("historical_note", ""):
            errors.append("historical invalid power note missing")
        out = ROOT / "data" / "benchmarks" / "experimental_2_9" / "reports"
        out.mkdir(parents=True, exist_ok=True)
        # Preserve historical sample_size_power.json; write corrected sibling
        full = power_report(n_sims=10_000)
        (out / "sample_size_power_2_13.json").write_text(
            json.dumps(full, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"paired_power primary={full.get('primary_planning_cell', {}).get('power')}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"power: {exc}")

    # 2) Bridge corpus
    try:
        bridge_root = ROOT / "data" / "benchmarks" / "experimental_2_13_bridges"
        report = generate_bridge_corpus(bridge_root)
        if not report["all_expectations_met"]:
            errors.append("bridge corpus expectations not met")
        for b in ALL_SCENARIO_BUILDERS:
            a = analyze_projection_diff(b())
            if not a["match_expectation"]:
                errors.append(f"bridge scenario fail: {a['scenario_id']}")
        print(f"bridge_corpus ok n={report['n_scenarios']}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"bridge: {exc}")

    # 3) Sampling determinism
    try:
        entries = [
            {
                "trace_id": f"x{i}",
                "fault_types": ["incomplete_trace"] if i % 2 else [],
                "topology_id": "sequential",
                "scale_tier": "S1",
            }
            for i in range(20)
        ]
        a = stratified_sample_entries(entries, n=8, seed=213)
        b = stratified_sample_entries(entries, n=8, seed=213)
        if a["selected_trace_ids"] != b["selected_trace_ids"]:
            errors.append("sampling non-deterministic")
        print("sampling ok")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"sampling: {exc}")

    # 4) Alignment disclosure present
    if "structurally aligned" not in ALIGNMENT_DISCLOSURE.lower():
        errors.append("ALIGNMENT_DISCLOSURE weak")

    # 5) Historical corpus preserved
    hist = ROOT / "data" / "benchmarks" / "experimental_2_9"
    if not (hist / "design_fingerprint.json").is_file():
        errors.append("experimental_2_9 design fingerprint missing")

    # 6) Compact results dir
    res = ROOT / "experiments" / "results" / "phase_2_13"
    res.mkdir(parents=True, exist_ok=True)
    (res / "phase_2_13_validator_status.json").write_text(
        json.dumps(
            {
                "ok": not errors,
                "errors": errors,
                "alignment_disclosure": ALIGNMENT_DISCLOSURE,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if errors:
        print("PHASE_2_13_VALIDATOR_FAIL", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        return 1
    print("PHASE_2_13_VALIDATOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
