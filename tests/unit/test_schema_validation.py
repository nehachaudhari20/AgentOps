"""Schema and validation unit tests."""

from __future__ import annotations

from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import EventCategory
from agenttrust.validation.validator import TraceValidator
from tests.conftest import make_artifact, make_event


def test_valid_event_record():
    v = TraceValidator()
    arts = [make_artifact("a1")]
    events = [make_event("e1", outputs=["a1"])]
    evs, arts_out, _, report = v.validate_trace(events=events, artifacts=arts)
    assert len(evs) == 1
    assert evs[0].event_id == "e1"
    assert "e1" in report.accepted_event_ids


def test_missing_required_event_field():
    v = TraceValidator()
    events = [{"trace_id": "t", "event_type": "prompt", "schema_version": "2.1.0"}]
    evs, _, _, report = v.validate_trace(events=events, artifacts=[])
    assert evs == []
    assert any(d.code == "missing_required_field" for d in report.diagnostics)


def test_invalid_timestamp():
    v = TraceValidator()
    events = [make_event("e1", ts_start="not-a-timestamp")]
    evs, _, _, report = v.validate_trace(events=events, artifacts=[])
    assert evs == []
    assert any(d.code == "invalid_timestamp" for d in report.diagnostics)


def test_end_before_start():
    v = TraceValidator()
    events = [
        make_event(
            "e1",
            ts_start="2024-01-01T01:00:00Z",
            ts_end="2024-01-01T00:00:00Z",
        )
    ]
    evs, _, _, report = v.validate_trace(events=events, artifacts=[])
    assert evs == []
    assert any(d.code == "invalid_timestamp_order" for d in report.diagnostics)


def test_unknown_event_type_maps_to_other():
    v = TraceValidator()
    events = [make_event("e1", event_type="quantum_florb")]
    # omit category so mapper applies
    events[0].pop("category", None)
    evs, _, _, report = v.validate_trace(events=events, artifacts=[])
    assert len(evs) == 1
    assert evs[0].category == EventCategory.OTHER
    assert any(d.code == "unknown_event_type" for d in report.diagnostics)


def test_duplicate_event_id_quarantined():
    v = TraceValidator()
    events = [make_event("e1"), make_event("e1", event_type="prompt")]
    evs, _, _, report = v.validate_trace(events=events, artifacts=[])
    assert len(evs) == 1
    assert "e1" in report.quarantined_event_ids
    assert any(d.code == "duplicate_event_id" for d in report.diagnostics)


def test_duplicate_artifact_id_conflict():
    v = TraceValidator()
    a1 = make_artifact("a1", content="one")
    a2 = make_artifact("a1", content="two")
    _, arts_out, _, report = v.validate_trace(events=[], artifacts=[a1, a2])
    assert len(arts_out) == 1
    assert "a1" in report.quarantined_artifact_ids
    assert any(d.code == "duplicate_artifact_id" for d in report.diagnostics)


def test_invalid_artifact_hash():
    v = TraceValidator()
    bad = {
        "artifact_id": "a1",
        "artifact_type": "blob",
        "content_hash": "not-a-hash",
        "schema_version": "2.1.0",
    }
    _, arts, _, report = v.validate_trace(events=[], artifacts=[bad])
    assert arts == []
    assert any(d.code == "invalid_content_hash" for d in report.diagnostics)


def test_optional_metadata_absent():
    v = TraceValidator()
    art = {
        "artifact_id": "a1",
        "artifact_type": "blob",
        "content_hash": "sha256:" + "ab" * 32,
        "schema_version": "2.1.0",
    }
    _, arts, _, report = v.validate_trace(events=[], artifacts=[art])
    assert len(arts) == 1
    assert arts[0].metadata == ()


def test_missing_status_is_unknown_not_success():
    v = TraceValidator()
    e = make_event("e1")
    del e["status"]
    evs, _, _, report = v.validate_trace(events=[e], artifacts=[])
    assert evs[0].status.value == "unknown"
    assert any(d.code == "missing_status" for d in report.diagnostics)
