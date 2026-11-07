"""Legacy migration tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agenttrust.migration.legacy_events import migrate_legacy_events_file, migrate_legacy_records
from agenttrust.provenance_trace import ProvenanceTrace

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "events.json"


def test_raw_events_loadable_and_unchanged(tmp_path):
    before = hashlib.sha256(RAW.read_bytes()).hexdigest()
    payload = migrate_legacy_events_file(RAW, tmp_path / "processed")
    after = hashlib.sha256(RAW.read_bytes()).hexdigest()
    assert before == after
    assert payload["migration_report"]["migrated_event_count"] == 14
    assert (tmp_path / "processed" / "events_v2.json").exists()


def test_migration_deterministic():
    legacy = json.loads(RAW.read_text(encoding="utf-8"))
    a = migrate_legacy_records(legacy, trace_id="t")
    b = migrate_legacy_records(legacy, trace_id="t")
    assert a["events"] == b["events"]
    assert a["artifacts"] == b["artifacts"]
    assert a["migration_report"]["migrated_artifact_count"] == b["migration_report"]["migrated_artifact_count"]


def test_missing_fields_reported_not_fabricated():
    legacy = [
        {
            "event_id": "x1",
            "agent_id": "A",
            "event_type": "prompt",
            "input_data": "hi",
            "output_data": "yo",
            "dependencies": [],
            "timestamp": 1.0,
            "metadata": {},
        }
    ]
    payload = migrate_legacy_records(legacy)
    reasons = {o["reason"] for o in payload["migration_report"]["omissions"]}
    assert "status_absent_in_source" in reasons
    assert "status" not in payload["events"][0]


def test_migrated_trace_loads_into_provenance_trace(tmp_path):
    payload = migrate_legacy_events_file(RAW, tmp_path / "processed")
    trace = ProvenanceTrace()
    report = trace.load_records(payload["events"], payload["artifacts"])
    assert len(report.accepted_event_ids) == 14
    assert trace.graph.number_of_nodes() > 14
    assert all("weight" not in d for _, _, _, d in trace.graph.edges(keys=True, data=True))
    assert len(trace.outcome_candidates()) >= 1
