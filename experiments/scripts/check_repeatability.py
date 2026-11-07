#!/usr/bin/env python3
"""
Deterministic repeatability checks (Phase 2.12).

Compares two independent runs of the same inputs for:
- provenance fingerprint
- RPA allocations
- MFAV vectors
- PLHC merkle root / verification status

Expected: bit-identical JSON for deterministic payloads (float equality within 1e-12).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust import AssuranceProfileCalculator, ConservedRPA, MFAV, PLHC, ProvenanceTrace
from agenttrust.evaluation.baselines import allocate_b0_uniform, allocate_rpa
from agenttrust.mlpg.projections import ProjectionKind


def _load_pilot_trace() -> ProvenanceTrace:
    pilot = ROOT / "data" / "benchmarks" / "pilot" / "traces"
    dirs = sorted(p for p in pilot.iterdir() if p.is_dir() and "clean" in p.name)
    if not dirs:
        dirs = sorted(p for p in pilot.iterdir() if p.is_dir())
    tdir = dirs[0]
    events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))["events"]
    arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]
    pt = ProvenanceTrace()
    pt.load_records(events, arts, default_trace_id=tdir.name)
    return pt


def _snapshot(pt: ProvenanceTrace) -> dict:
    outcomes = pt.outcome_candidates()
    oid = outcomes[0] if outcomes else None
    out: dict = {
        "fingerprint": pt.fingerprint(),
        "completeness": pt.completeness().to_dict(),
    }
    if oid:
        r1 = allocate_rpa(pt, oid, projection_kind=ProjectionKind.P1_DIRECT)
        r2 = allocate_rpa(pt, oid, projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE)
        b0 = allocate_b0_uniform(pt, oid)
        out["rpa_p1"] = r1.to_dict()
        out["rpa_p2"] = r2.to_dict()
        out["b0"] = b0.to_dict()
        if r1.status == "ok":
            # Rebuild RPAResult-like via allocate_from_trace for MFAV
            rr = ConservedRPA().allocate_from_trace(pt, [oid], projection_kind=ProjectionKind.P1_DIRECT)[0]
            mfav = MFAV().compute(rr, trace=pt)
            out["mfav"] = mfav.to_dict()
    plhc = PLHC()
    snap = plhc.build_snapshot(pt)
    cp = plhc.create_checkpoint(snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00")
    ver = plhc.verify_against_checkpoint(pt, cp)
    out["plhc"] = {
        "merkle_root": snap.merkle_root,
        "leaf_count": snap.leaf_count,
        "status": ver.status.value,
    }
    # Assurance profile (deterministic payload)
    rpa_res = None
    mfav_res = None
    if oid and out.get("rpa_p1", {}).get("status") == "ok":
        try:
            rpa_res = ConservedRPA().allocate_from_trace(
                pt, [oid], projection_kind=ProjectionKind.P1_DIRECT
            )[0]
            mfav_res = MFAV().compute(rpa_res, trace=pt)
        except Exception:  # noqa: BLE001
            pass
    profile = AssuranceProfileCalculator().compute(
        pt, rpa_result=rpa_res, mfav_result=mfav_res, plhc_result=ver
    )
    out["assurance"] = profile.to_dict()
    return out


def _eq(a, b, path="$") -> list[str]:
    diffs = []
    if type(a) != type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return [f"{path}: type {type(a)} vs {type(b)}"]
    if isinstance(a, dict):
        if set(a) != set(b):
            return [f"{path}: keys {set(a)^set(b)}"]
        for k in a:
            diffs.extend(_eq(a[k], b[k], f"{path}.{k}"))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: len {len(a)} vs {len(b)}"]
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(_eq(x, y, f"{path}[{i}]"))
        return diffs
    if isinstance(a, float) or isinstance(b, float):
        if abs(float(a) - float(b)) > 1e-12:
            diffs.append(f"{path}: {a} vs {b}")
        return diffs
    if a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")
    return diffs


def main() -> int:
    pt = _load_pilot_trace()
    a = _snapshot(pt)
    # Fresh reload for independence
    pt2 = _load_pilot_trace()
    b = _snapshot(pt2)
    diffs = _eq(a, b)
    report = {
        "ok": not diffs,
        "n_diffs": len(diffs),
        "diffs": diffs[:50],
        "trace_fingerprint": a.get("fingerprint"),
        "expectation": "bit-identical deterministic payloads; floats within 1e-12",
    }
    out = ROOT / "experiments" / "results" / "repro_scratch" / "repeatability_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "n_diffs": report["n_diffs"], "report": str(out.as_posix())}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
