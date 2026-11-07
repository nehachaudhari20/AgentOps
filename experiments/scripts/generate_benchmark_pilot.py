#!/usr/bin/env python3
"""Generate the Phase 2.4 pilot synthetic benchmark corpus."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark import (
    BenchmarkGenerator,
    pilot_configs,
    validate_generated_trace,
)


def main() -> int:
    out = ROOT / "data" / "benchmarks" / "pilot"
    traces_dir = out / "traces"
    gt_dir = out / "ground_truth"
    man_dir = out / "manifests"
    traces_dir.mkdir(parents=True, exist_ok=True)

    gen = BenchmarkGenerator()
    configs = pilot_configs(seeds=(1, 2), include_fault_samples=True)

    summary = {
        "generator_version": gen.generator_version,
        "n_configs": len(configs),
        "traces": [],
        "validation_failures": [],
        "totals": {},
    }

    event_counts: list[int] = []
    agent_counts: list[int] = []
    topology_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    fault_counts: Counter[str] = Counter()
    n_fault_free = 0
    n_fault = 0
    n_incomplete = 0
    n_outcomes = 0
    agents_global: set[str] = set()
    n_artifacts = 0
    n_events = 0

    for cfg in configs:
        trace = gen.generate(cfg)
        paths = gen.write_trace(
            trace,
            events_dir=traces_dir,
            ground_truth_dir=gt_dir,
            manifests_dir=man_dir,
        )
        # Require complete only for clean traces
        require_complete = not (cfg.incomplete or cfg.fault_types)
        v = validate_generated_trace(trace, require_complete=require_complete)
        if not v.ok:
            summary["validation_failures"].append(
                {"trace_id": trace.manifest.trace_id, "errors": v.errors}
            )

        m = trace.manifest
        event_counts.append(m.actual_event_count)
        agent_counts.append(m.agent_count)
        topology_counts[m.topology_id] += 1
        scenario_counts[m.scenario_id] += 1
        n_events += m.actual_event_count
        n_artifacts += m.artifact_count
        n_outcomes += len(m.outcome_event_ids)
        agents_global.update(m.agent_ids)
        if m.fault_types:
            n_fault += 1
            for f in m.fault_types:
                fault_counts[f] += 1
        else:
            n_fault_free += 1
        if m.incomplete:
            n_incomplete += 1

        summary["traces"].append(
            {
                "trace_id": m.trace_id,
                "paths": {k: p.relative_to(ROOT).as_posix() for k, p in paths.items()},
                "actual_event_count": m.actual_event_count,
                "agent_count": m.agent_count,
                "artifact_count": m.artifact_count,
                "intervention_count": m.intervention_count,
                "incomplete": m.incomplete,
                "fault_types": m.fault_types,
                "validation_ok": v.ok,
            }
        )

    def _dist(values: list[int]) -> dict:
        if not values:
            return {}
        return {
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "n": len(values),
        }

    summary["totals"] = {
        "n_traces": len(configs),
        "n_events": n_events,
        "n_artifacts": n_artifacts,
        "n_unique_agents": len(agents_global),
        "n_outcomes": n_outcomes,
        "n_fault_free_traces": n_fault_free,
        "n_fault_injected_traces": n_fault,
        "n_intentionally_incomplete_traces": n_incomplete,
        "event_count_distribution": _dist(event_counts),
        "agent_count_distribution": _dist(agent_counts),
        "topology_distribution": dict(topology_counts),
        "scenario_distribution": dict(scenario_counts),
        "fault_distribution": dict(fault_counts),
        "n_validation_failures": len(summary["validation_failures"]),
    }

    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary["totals"], indent=2))
    print(f"Wrote {summary_path}")
    if summary["validation_failures"]:
        print(f"VALIDATION FAILURES: {len(summary['validation_failures'])}", file=sys.stderr)
        for item in summary["validation_failures"][:10]:
            print(item, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
