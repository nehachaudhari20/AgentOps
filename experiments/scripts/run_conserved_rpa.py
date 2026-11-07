"""Demo: conserved RPA on migrated Phase 2.1 processed events (P1 and P2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agenttrust import ConservedRPA, ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind


def main() -> None:
    repo = _REPO
    events = json.loads((repo / "data" / "processed" / "events_v2.json").read_text(encoding="utf-8"))
    arts = json.loads((repo / "data" / "processed" / "artifacts_v2.json").read_text(encoding="utf-8"))

    trace = ProvenanceTrace()
    report = trace.load_records(events["events"], arts["artifacts"])
    print("Validation accepted events:", len(report.accepted_event_ids))
    print("Completeness:", trace.completeness().to_dict())
    print("Outcomes:", trace.outcome_candidates())

    engine = ConservedRPA()
    for kind in (ProjectionKind.P1_DIRECT, ProjectionKind.P2_ARTIFACT_BRIDGE):
        results = engine.allocate_from_trace(trace, projection_kind=kind)
        for r in results:
            print(f"\n=== {r.projection_kind} outcome={r.outcome_id} alpha={r.alpha} ===")
            print("Conservation:", r.conservation)
            roots = sorted(r.root_allocations.items(), key=lambda x: -x[1])
            print("Root allocations:")
            for node, val in roots:
                agent = trace.graph.nodes[node].get("agent_id")
                print(f"  {node[:8]}… agent={agent}: {val:.6f}")


if __name__ == "__main__":
    main()
