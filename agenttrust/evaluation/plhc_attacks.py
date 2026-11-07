"""
Controlled PLHC integrity attacks for Phase 2.10–2.13 RQ5.

Threat model: tamper-evident relative to a retained honest checkpoint —
NOT immutable storage, NOT external anchoring, NOT protection if attacker
rewrites both evidence and checkpoint.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Optional

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
        if events and events[0].get("output_artifact_ids"):
            events[0]["output_artifact_ids"] = []
        elif events:
            events[0]["status"] = (
                "failure" if events[0].get("status") != "failure" else "success"
            )
        return _clone_load(events, arts)
    events.pop(0)
    return _clone_load(events, arts)


def attack_remove_artifact(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if arts:
        arts.pop(0)
    elif events:
        # No artifact to delete — flip status so attack is still a mutation
        events[0]["status"] = "failure" if events[0].get("status") != "failure" else "success"
    return _clone_load(events, arts)


def attack_relationship_modify(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if len(events) >= 2:
        # Corrupt dependency: point second event at a phantom or clear deps
        deps = list(events[1].get("dependency_event_ids") or [])
        if deps:
            events[1]["dependency_event_ids"] = ["phantom:" + deps[0]]
        else:
            events[1]["dependency_event_ids"] = [events[0]["event_id"]]
            # Then flip to ensure change vs original if original already had that
            events[1]["dependency_event_ids"] = ["phantom:rel"]
    elif events:
        events[0]["status"] = "failure" if events[0].get("status") != "failure" else "success"
    return _clone_load(events, arts)


def attack_reorder_events(trace: ProvenanceTrace) -> ProvenanceTrace:
    """
    Temporal reordering via altered event timestamps.

    Mere list permutation is a no-op under ID-sorted Merkle canonicalization.
    This attack shifts event[0] timestamps so leaf payloads change.
    """
    events, arts = _public_events_arts(trace)
    if events:
        # Force a detectable temporal mutation even if original stamps were equal
        events[0]["ts_start"] = "1999-01-01T00:00:00+00:00"
        events[0]["ts_end"] = "1999-01-01T00:00:01+00:00"
        if len(events) >= 2:
            events[1]["ts_start"] = "2099-12-31T23:59:58+00:00"
            events[1]["ts_end"] = "2099-12-31T23:59:59+00:00"
    return _clone_load(events, arts)


def attack_identity_substitution(trace: ProvenanceTrace) -> ProvenanceTrace:
    events, arts = _public_events_arts(trace)
    if events:
        events[0]["agent_id"] = "ATTACKER_SUBSTITUTED_AGENT"
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


def attack_checkpoint_chain(cp: IntegrityCheckpoint) -> IntegrityCheckpoint:
    return IntegrityCheckpoint(
        sequence_number=cp.sequence_number,
        previous_checkpoint_hash="f" * 64,
        merkle_root=cp.merkle_root,
        leaf_count=cp.leaf_count,
        canonicalization_version=cp.canonicalization_version,
        hash_algorithm=cp.hash_algorithm,
        checkpoint_format_version=cp.checkpoint_format_version,
        merkle_format_version=cp.merkle_format_version,
        created_at=cp.created_at,
        checkpoint_hash=cp.checkpoint_hash,
    )


# Evidence mutations (applied to trace; checkpoint held honest)
EVIDENCE_ATTACKS: dict[str, AttackFn] = {
    "event_payload_change": attack_event_payload,
    "artifact_content_change": attack_artifact_content,
    "leaf_removal_via_event_delete": attack_remove_event,
    "artifact_deletion": attack_remove_artifact,
    "relationship_modification": attack_relationship_modify,
    "event_reordering": attack_reorder_events,
    "identity_substitution": attack_identity_substitution,
}

# Backward-compatible alias
ATTACKS = EVIDENCE_ATTACKS


def evaluate_plhc_attacks(trace: ProvenanceTrace) -> dict[str, Any]:
    plhc = PLHC()
    snap = plhc.build_snapshot(trace)
    cp = plhc.create_checkpoint(
        snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00"
    )
    clean = plhc.verify_against_checkpoint(trace, cp)
    results: dict[str, Any] = {
        "clean_control": {
            "status": clean.status.value,
            "ok": clean.status == IntegrityStatus.VERIFIED,
        },
        "attacks": {},
        "threat_model": (
            "tamper-evident relative to honestly retained checkpoint; "
            "not immutability; not external anchoring; not dual-rewrite resistant"
        ),
    }
    for name, fn in EVIDENCE_ATTACKS.items():
        tampered = fn(trace)
        ver = plhc.verify_against_checkpoint(tampered, cp)
        results["attacks"][name] = {
            "class": "evidence_modification",
            "status": ver.status.value,
            "detected": ver.status != IntegrityStatus.VERIFIED,
        }
    bad_cp = attack_checkpoint_root(cp)
    ver_cp = plhc.verify_against_checkpoint(trace, bad_cp)
    results["attacks"]["checkpoint_alteration"] = {
        "class": "checkpoint_modification",
        "status": ver_cp.status.value,
        "detected": ver_cp.status != IntegrityStatus.VERIFIED,
    }
    bad_chain = attack_checkpoint_chain(cp)
    ver_chain = plhc.verify_against_checkpoint(trace, bad_chain)
    results["attacks"]["checkpoint_chain_alteration"] = {
        "class": "checkpoint_chain",
        "status": ver_chain.status.value,
        "detected": ver_chain.status != IntegrityStatus.VERIFIED,
    }
    return results
