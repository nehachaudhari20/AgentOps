"""Integration: pipeline on historical pilot corpus samples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrust.pipeline import AgentTrustPipeline, PipelineConfig

ROOT = Path(__file__).resolve().parents[2]
PILOT_TRACES = ROOT / "data" / "benchmarks" / "pilot" / "traces"


@pytest.mark.skipif(not PILOT_TRACES.is_dir(), reason="pilot corpus not present")
def test_pilot_sample_trace_end_to_end():
    dirs = sorted(p for p in PILOT_TRACES.iterdir() if p.is_dir())
    assert dirs, "pilot traces empty"
    # Prefer a clean complete-looking name
    preferred = [d for d in dirs if "clean" in d.name and "inc" not in d.name]
    tdir = preferred[0] if preferred else dirs[0]
    res = AgentTrustPipeline().run_trace_dir(tdir)
    assert res.provenance_fingerprint is not None
    assert res.plhc["status"] == "ok"
    assert res.assurance["status"] == "ok"
    payload = res.deterministic_payload()
    # Round-trip JSON stability
    blob = json.dumps(payload, sort_keys=True)
    assert json.loads(blob) == payload


@pytest.mark.skipif(not PILOT_TRACES.is_dir(), reason="pilot corpus not present")
def test_pilot_incomplete_trace_not_concealed():
    incomplete = [
        p
        for p in PILOT_TRACES.iterdir()
        if p.is_dir() and ("incomplete" in p.name or p.name.endswith("-inc"))
    ]
    if not incomplete:
        pytest.skip("no incomplete pilot traces")
    res = AgentTrustPipeline().run_trace_dir(incomplete[0])
    assert res.graph_summary.get("completeness", {}).get("incomplete") is True
    # Default config must not silently complete RPA on incomplete traces
    assert res.config["allow_incomplete_rpa"] is False
    assert res.rpa["status"] == "ineligible"
    assert any("incomplete" in w.lower() for w in res.warnings)
    # PLHC/assurance still run; incompleteness is explicit, not concealed
    assert res.plhc["status"] == "ok"
    assert res.assurance["status"] == "ok"


@pytest.mark.skipif(not PILOT_TRACES.is_dir(), reason="pilot corpus not present")
def test_pilot_determinism_on_one_trace():
    dirs = sorted(p for p in PILOT_TRACES.iterdir() if p.is_dir() and "clean" in p.name)
    tdir = dirs[0]
    pipe = AgentTrustPipeline(PipelineConfig(primary_outcome_only=True))
    a = pipe.run_trace_dir(tdir).deterministic_payload()
    b = pipe.run_trace_dir(tdir).deterministic_payload()
    assert a == b
