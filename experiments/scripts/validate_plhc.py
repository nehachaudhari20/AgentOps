#!/usr/bin/env python3
"""
PLHC fail-closed validation over historical pilot + fault-matrix corpora.

Exit 0 only if every trace builds a deterministic snapshot and verifies
against its genesis checkpoint. Any mismatch → non-zero exit after report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust import PLHC, ProvenanceTrace


def _eval_corpus(traces_root: Path, label: str) -> dict:
    report = {
        "corpus": label,
        "n_examined": 0,
        "n_verified": 0,
        "n_errors": 0,
        "roots": {},
        "errors": [],
    }
    if not traces_root.is_dir():
        report["n_errors"] += 1
        report["errors"].append({"error": f"missing corpus: {traces_root}"})
        return report

    plhc = PLHC()
    dirs = sorted(p for p in traces_root.iterdir() if p.is_dir())
    report["n_examined"] = len(dirs)
    for tdir in dirs:
        try:
            events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
            arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
            pt = ProvenanceTrace()
            pt.load_records(events, arts)
            snap1 = plhc.build_snapshot(pt)
            snap2 = plhc.build_snapshot(pt)
            if snap1.merkle_root != snap2.merkle_root:
                raise RuntimeError("non-deterministic merkle_root")
            cp = plhc.create_checkpoint(snap1, sequence_number=0)
            result = plhc.verify_against_checkpoint(pt, cp)
            if result.status.value != "verified":
                raise RuntimeError(result.explanation)
            # inclusion proof for first leaf if any
            if snap1.leaves:
                proof = plhc.prove_inclusion(snap1, snap1.leaves[0].leaf_id)
                if not plhc.verify_inclusion(proof, expected_root=snap1.merkle_root):
                    raise RuntimeError("inclusion proof failed")
            report["n_verified"] += 1
            report["roots"][tdir.name] = snap1.merkle_root
        except Exception as exc:
            report["n_errors"] += 1
            report["errors"].append({"trace_id": tdir.name, "error": str(exc)})
    return report


def main() -> int:
    out = ROOT / "experiments" / "results" / "plhc_phase27"
    out.mkdir(parents=True, exist_ok=True)
    pilot = _eval_corpus(ROOT / "data" / "benchmarks" / "pilot" / "traces", "pilot")
    matrix = _eval_corpus(
        ROOT / "data" / "benchmarks" / "phase25_fault_matrix" / "traces", "fault_matrix"
    )
    summary = {"pilot": pilot, "fault_matrix": matrix}
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    errors = pilot["n_errors"] + matrix["n_errors"]
    if errors:
        print(f"FAIL-CLOSED: {errors} PLHC error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
