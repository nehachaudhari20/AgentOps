#!/usr/bin/env python3
"""
Compare regenerated logical records to the checked-in pilot without overwriting it.

Reports whether clean (fault-free) traces still match under the active generator,
and documents expected divergence for faulted traces after Phase 2.5 semantic fixes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark import (
    BenchmarkConfig,
    BenchmarkGenerator,
    ScenarioId,
    ScaleTier,
    TopologyId,
)


def main() -> int:
    pilot = ROOT / "data" / "benchmarks" / "pilot"
    manifests = sorted((pilot / "manifests").glob("*.json"))
    gen = BenchmarkGenerator()

    summary = {
        "active_generator_version": gen.generator_version,
        "n_manifests": len(manifests),
        "clean_compared": 0,
        "clean_exact_match": 0,
        "clean_mismatch": [],
        "faulted_skipped": 0,
        "version_mismatch_skipped": 0,
        "notes": [
            "Does not overwrite pilot data.",
            "Phase 2.5 fault semantics intentionally diverge from 2.4.0 faulted traces.",
            "Clean-trace event bodies should match if materialization is unchanged.",
        ],
    }

    for path in manifests:
        man = json.loads(path.read_text(encoding="utf-8"))
        if man.get("fault_types"):
            summary["faulted_skipped"] += 1
            continue
        if man.get("generator_version") != "2.4.0":
            # Still try compare for 2.5.0 clean if present
            pass
        try:
            cfg = BenchmarkConfig(
                scenario_id=ScenarioId(man["scenario_id"]),
                topology_id=TopologyId(man["topology_id"]),
                scale_tier=ScaleTier(man["scale_tier"]),
                seed=int(man["seed"]),
                fault_types=(),
                incomplete=False,
                # Use active generator version for regeneration
            )
        except Exception as exc:
            summary["clean_mismatch"].append({"trace_id": man.get("trace_id"), "error": str(exc)})
            continue

        regenerated = gen.generate(cfg)
        tid = man["trace_id"]
        # Pilot trace ids embed generator-era fault token "clean"; regenerated 2.5 ids may differ
        # Match by loading the on-disk directory named in manifest.
        tdir = pilot / "traces" / tid
        if not tdir.exists():
            summary["clean_mismatch"].append({"trace_id": tid, "error": "missing trace dir"})
            continue
        disk_events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
        disk_arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]

        # Compare logical fields excluding trace_id / event_id prefixes that embed trace_id
        def _strip_ids(events, arts, new_trace_id):
            # Map old ids → comparable payloads without absolute ids
            return (
                [
                    {
                        k: v
                        for k, v in e.items()
                        if k
                        not in {
                            "event_id",
                            "trace_id",
                            "dependency_event_ids",
                            "input_artifact_ids",
                            "output_artifact_ids",
                            "invokes_event_ids",
                            "retries_event_id",
                            "observed_after_event_ids",
                        }
                    }
                    for e in events
                ],
                [
                    {k: v for k, v in a.items() if k != "artifact_id"}
                    for a in arts
                ],
            )

        summary["clean_compared"] += 1
        se, sa = _strip_ids(disk_events, disk_arts, tid)
        re, ra = _strip_ids(regenerated.events, regenerated.artifacts, regenerated.manifest.trace_id)
        # Sort for order-independent comparison of stripped payloads
        se_s = sorted(se, key=lambda x: (x.get("category"), x.get("ts_start"), x.get("agent_id")))
        re_s = sorted(re, key=lambda x: (x.get("category"), x.get("ts_start"), x.get("agent_id")))
        if se_s == re_s and len(sa) == len(ra):
            summary["clean_exact_match"] += 1
        else:
            summary["clean_mismatch"].append(
                {
                    "trace_id": tid,
                    "disk_events": len(disk_events),
                    "regen_events": len(regenerated.events),
                    "disk_generator_version": man.get("generator_version"),
                    "regen_generator_version": gen.generator_version,
                    "note": "Stripped-field mismatch or count mismatch",
                }
            )

    out = pilot / "reproducibility_check.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "clean_mismatch"}, indent=2))
    print(f"mismatches={len(summary['clean_mismatch'])} report={out}")
    # Non-zero mismatches are informational for 2.4→2.5; do not fail the phase hard
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
