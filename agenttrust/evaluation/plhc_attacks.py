"""
Controlled PLHC integrity attacks for Phase 2.10 ablations / Phase 2.11 RQ5.

Threat model: tamper-evident relative to a retained checkpoint — not immutable storage.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from agenttrust.integrity.checkpoint import IntegrityCheckpoint
from agenttrust.integrity.result import IntegrityStatus
from agenttrust.integrity.verifier import PLHC
from agenttrust.provenance_trace import ProvenanceTrace


AttackFn = Callable[[ProvenanceTrace], ProvenanceTrace]


def _clone_load(events, arts) -> ProvenanceTrace:
    pt = ProvenanceTrace()
    pt.load_records(copy.deepcopy(events), copy.deepcopy(arts))
    return pt


def _public_events_arts(trace: ProvenanceTrace) -> tuple[list[dict], list[dict]]:
    events = [e.to_public_dict() for e in trace.events]
    arts = [a.to_public_dict() for a in trace.artifacts]
    return events, arts


def attack_event_payload(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if events:
        events[0]["status"] = "failure" if events[0].get("status") != "failure" else "success"
    return _clone_load(events, arts)


def attack_artifact_content(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if arts:
        arts[0]["content_hash"] = "sha256:" + ("a" * 64)
    return _clone_load(events, arts)


def attack_remove_event(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if len(events) <= 1:
        # Ensure a detectable change even on tiny traces: drop sole event's deps noise
        # by clearing an output artifact link when present; else flip status.
        if events and events[0].get("output_artifact_ids"):
            events[0]["output_artifact_ids"] = []
        elif events:
            events[0]["status"] = (
                "failure" if events[0].get("status") != "failure" else "success"
            )
        return _clone_load(events, arts)
    # Prefer removing a non-last event to keep an outcome-like node when possible
    events.pop(0)
    return _clone_load(events, arts)


def attack_checkpoint_root(cp: IntegrityCheckpoint) -> IntegrityCheckpoint:
    return IntegrityCheckpoint(
        sequence_number=cp.sequence_number,
        previous_checkpoint_hash=cp.previous_checkpoint_hash,
        merkle_root="0" * 64,
        leaf_count=cp.leaf_count,
        canonicalization_version=cp.canonicalization_version,
        hash_algorithm=cp.hash_algorithm,
        checkpoint_format_version=cp.checkpoint_format_version,
        merkle_format_version=cp.merkle_format_version,
        created_at=cp.created_at,
        checkpoint_hash=cp.checkpoint_hash,
    )


ATTACKS: dict[str, AttackFn] = {
    "event_payload_change": attack_event_payload,
    "artifact_content_change": attack_artifact_content,
    "leaf_removal_via_event_delete": attack_remove_event,
}


def evaluate_plhc_attacks(trace: ProvenanceTrace) -> dict[str, Any]:
    plhc = PLHC()
    snap = plhc.build_snapshot(trace)
    cp = plhc.create_checkpoint(
        snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00"
    )
    clean = plhc.verify_against_checkpoint(trace, cp)
    results = {
        "clean_control": {
            "status": clean.status.value,
            "ok": clean.status == IntegrityStatus.VERIFIED,
        },
        "attacks": {},
    }
    for name, fn in ATTACKS.items():
        tampered = fn(trace)
        ver = plhc.verify_against_checkpoint(tampered, cp)
        results["attacks"][name] = {
            "status": ver.status.value,
            "detected": ver.status != IntegrityStatus.VERIFIED,
        }
    # Checkpoint alteration
    bad_cp = attack_checkpoint_root(cp)
    ver_cp = plhc.verify_against_checkpoint(trace, bad_cp)
    results["attacks"]["checkpoint_alteration"] = {
        "status": ver_cp.status.value,
        "detected": ver_cp.status != IntegrityStatus.VERIFIED,
    }
    return results
