"""Phase 2.12 reproducibility helpers."""

from __future__ import annotations

from agenttrust.repro.manifest import build_run_manifest


def test_manifest_excludes_timing_from_content_hash():
    m1 = build_run_manifest(
        run_id="t",
        stage="env",
        commands=["python -V"],
        started_at="2020-01-01T00:00:00+00:00",
        ended_at="2020-01-01T00:00:01+00:00",
    )
    m2 = build_run_manifest(
        run_id="t",
        stage="env",
        commands=["python -V"],
        started_at="2099-01-01T00:00:00+00:00",
        ended_at="2099-01-01T00:00:01+00:00",
    )
    assert m1.content_hash() == m2.content_hash()
    d = m1.to_dict()
    assert "content_hash_sha256" in d
    assert "started_at" in d
