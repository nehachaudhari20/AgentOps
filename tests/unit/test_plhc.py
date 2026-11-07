"""Phase 2.7 PLHC adversarial and determinism tests."""

from __future__ import annotations

import copy
import math
from dataclasses import replace

import pytest

from agenttrust import (
    AssuranceProfileCalculator,
    AssuranceStatus,
    IntegrityStatus,
    PLHC,
    ProvenanceTrace,
)
from agenttrust.integrity.canonicalization import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonicalize,
)
from agenttrust.integrity.checkpoint import (
    GENESIS_PREV_HASH,
    create_checkpoint,
    verify_checkpoint_chain,
)
from agenttrust.integrity.leaves import (
    artifact_payload,
    build_all_leaves,
    build_artifact_leaf,
    build_event_leaf,
)
from agenttrust.integrity.merkle import (
    InclusionProof,
    build_merkle_tree,
    prove_inclusion,
    verify_inclusion,
)
from agenttrust.integrity.result import IntegrityVerificationResult
from agenttrust.schema.enums import RelationshipType
from agenttrust.schema.relationship import RelationshipRecord
from tests.conftest import make_artifact, make_event


def _load(events, arts=None, rels=None) -> ProvenanceTrace:
    t = ProvenanceTrace()
    t.load_records(events, arts or [], rels)
    return t


def _simple_trace() -> ProvenanceTrace:
    arts = [make_artifact("a1", "payload-a")]
    events = [
        make_event("e1", category="reasoning", outputs=["a1"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"], inputs=["a1"]),
    ]
    return _load(events, arts)


# --- Canonicalization ---


def test_canon_dict_insertion_order_independent():
    a = canonicalize({"b": 1, "a": 2})
    b = canonicalize({"a": 2, "b": 1})
    assert a == b


def test_canon_type_distinctions():
    assert canonicalize(None) != canonicalize(0)
    assert canonicalize(True) != canonicalize(1)
    assert canonicalize(1) != canonicalize(1.0)
    assert canonicalize("1") != canonicalize(1)


def test_canon_unicode_deterministic():
    s = "café — 日本語"
    assert canonicalize({"t": s}) == canonicalize({"t": s})
    assert canonicalize({"t": s}).decode("utf-8")


def test_canon_rejects_nan_inf():
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": float("nan")})
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": float("inf")})
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": float("-inf")})


def test_canon_rejects_unsupported():
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": object()})


def test_duplicate_event_ids_rejected():
    from agenttrust.integrity.leaves import LeafConstructionError

    t = _simple_trace()
    # Bypass schema uniqueness: feed duplicate EventRecords into leaf builder
    with pytest.raises(LeafConstructionError):
        build_all_leaves(
            (t.events[0], t.events[0]),
            t.artifacts,
            t.relationships,
        )


# --- Leaves / tampering ---


def test_storage_uri_excluded_from_artifact_commitment():
    a1 = make_artifact("a1", "x")
    a1["storage_uri"] = "s3://secret/bucket/obj"
    a2 = make_artifact("a1", "x")
    a2["storage_uri"] = "file:///other/path"
    t1 = _load([make_event("e1", outputs=["a1"])], [a1])
    t2 = _load([make_event("e1", outputs=["a1"])], [a2])
    assert PLHC().build_snapshot(t1).merkle_root == PLHC().build_snapshot(t2).merkle_root
    # payload must not include storage_uri
    leaf = build_artifact_leaf(t1.artifacts[0])
    assert "storage_uri" not in leaf.payload


def test_event_status_change_changes_hash():
    t1 = _simple_trace()
    h1 = build_event_leaf(t1.events[0]).content_hash
    ev = dict(t1.events[0].to_public_dict())
    ev["status"] = "failure"
    t2 = _load(
        [ev, t1.events[1].to_public_dict()],
        [a.to_public_dict() for a in t1.artifacts],
    )
    # find same event_id
    e = next(e for e in t2.events if e.event_id == t1.events[0].event_id)
    assert build_event_leaf(e).content_hash != h1


def test_event_timestamp_change_changes_hash():
    from datetime import datetime, timezone

    t1 = _simple_trace()
    e0 = t1.events[0]
    h1 = build_event_leaf(e0).content_hash
    e_mod = replace(e0, ts_start=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert build_event_leaf(e_mod).content_hash != h1


def test_event_io_ref_change_changes_hash():
    arts = [make_artifact("a1"), make_artifact("a2")]
    t1 = _load([make_event("e1", outputs=["a1"])], arts)
    t2 = _load([make_event("e1", outputs=["a2"])], arts)
    assert build_event_leaf(t1.events[0]).content_hash != build_event_leaf(t2.events[0]).content_hash


def test_artifact_content_hash_change_changes_leaf():
    t1 = _load([make_event("e1", outputs=["a1"])], [make_artifact("a1", "one")])
    t2 = _load([make_event("e1", outputs=["a1"])], [make_artifact("a1", "two")])
    assert build_artifact_leaf(t1.artifacts[0]).content_hash != build_artifact_leaf(
        t2.artifacts[0]
    ).content_hash


def test_artifact_type_change_changes_leaf():
    a1 = make_artifact("a1", "x")
    a2 = make_artifact("a1", "x")
    a2["artifact_type"] = "other"
    t1 = _load([make_event("e1", outputs=["a1"])], [a1])
    t2 = _load([make_event("e1", outputs=["a1"])], [a2])
    assert build_artifact_leaf(t1.artifacts[0]).content_hash != build_artifact_leaf(
        t2.artifacts[0]
    ).content_hash


def test_relationship_type_change_changes_root():
    arts = [make_artifact("a1")]
    events = [
        make_event("e1", outputs=["a1"]),
        make_event("e2", deps=["e1"], inputs=["a1"]),
    ]
    t1 = _load(events, arts)
    root1 = PLHC().build_snapshot(t1).merkle_root
    # Force an OBSERVED_AFTER in addition / replace by rebuilding with observed_after
    events2 = [
        make_event("e1", outputs=["a1"]),
        make_event("e2", deps=["e1"], inputs=["a1"], observed_after_event_ids=["e1"]),
    ]
    t2 = _load(events2, arts)
    root2 = PLHC().build_snapshot(t2).merkle_root
    assert root1 != root2


def test_relationship_endpoint_change_changes_root():
    arts = [make_artifact("a1"), make_artifact("a2")]
    t1 = _load([make_event("e1", outputs=["a1"])], arts)
    t2 = _load([make_event("e1", outputs=["a2"])], arts)
    assert PLHC().build_snapshot(t1).merkle_root != PLHC().build_snapshot(t2).merkle_root


def test_deleted_relationship_changes_root():
    arts = [make_artifact("a1")]
    t1 = _load(
        [
            make_event("e1", outputs=["a1"]),
            make_event("e2", deps=["e1"], inputs=["a1"]),
        ],
        arts,
    )
    t2 = _load(
        [
            make_event("e1", outputs=["a1"]),
            make_event("e2", inputs=["a1"]),  # no deps
        ],
        arts,
    )
    assert PLHC().build_snapshot(t1).merkle_root != PLHC().build_snapshot(t2).merkle_root


def test_added_relationship_changes_root():
    arts = [make_artifact("a1")]
    t1 = _load([make_event("e1", outputs=["a1"]), make_event("e2", inputs=["a1"])], arts)
    t2 = _load(
        [make_event("e1", outputs=["a1"]), make_event("e2", deps=["e1"], inputs=["a1"])],
        arts,
    )
    assert PLHC().build_snapshot(t1).merkle_root != PLHC().build_snapshot(t2).merkle_root


def test_observed_after_committed_not_causal():
    arts = [make_artifact("a1")]
    events = [
        make_event("e1", outputs=["a1"]),
        make_event("e2", inputs=["a1"], observed_after_event_ids=["e1"]),
    ]
    t = _load(events, arts)
    snap = PLHC().build_snapshot(t)
    rel_leaves = [leaf for leaf in snap.leaves if leaf.kind == "relationship"]
    assert any(leaf.payload.get("rel_type") == "OBSERVED_AFTER" for leaf in rel_leaves)
    # documentation / limitation: not causal — presence in commitment only
    assert any(leaf.payload["rel_type"] == "OBSERVED_AFTER" for leaf in rel_leaves)


def test_graph_insertion_order_independent_root():
    arts = [make_artifact("a1"), make_artifact("a2")]
    e_fwd = [
        make_event("e1", outputs=["a1"]),
        make_event("e2", outputs=["a2"], deps=["e1"]),
    ]
    e_rev = list(reversed(e_fwd))
    a_rev = list(reversed(arts))
    r1 = PLHC().build_snapshot(_load(e_fwd, arts)).merkle_root
    r2 = PLHC().build_snapshot(_load(e_rev, a_rev)).merkle_root
    assert r1 == r2


# --- Merkle ---


def test_inclusion_proof_valid():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    leaf_id = snap.leaves[0].leaf_id
    proof = plhc.prove_inclusion(snap, leaf_id)
    assert plhc.verify_inclusion(proof, expected_root=snap.merkle_root)


def test_inclusion_wrong_leaf_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    proof = plhc.prove_inclusion(snap, snap.leaves[0].leaf_id)
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash="0" * 64,
        leaf_count=proof.leaf_count,
        siblings=proof.siblings,
        root=proof.root,
    )
    assert not plhc.verify_inclusion(bad, expected_root=snap.merkle_root)


def test_inclusion_wrong_root_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    proof = plhc.prove_inclusion(snap, snap.leaves[0].leaf_id)
    assert not plhc.verify_inclusion(proof, expected_root="a" * 64)


def test_inclusion_modified_sibling_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    proof = plhc.prove_inclusion(snap, snap.leaves[0].leaf_id)
    if not proof.siblings:
        pytest.skip("single-path has no siblings")
    sibs = list(proof.siblings)
    side, h = sibs[0]
    sibs[0] = (side, ("b" if h[0] == "a" else "a") + h[1:])
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=tuple(sibs),
        root=proof.root,
    )
    assert not plhc.verify_inclusion(bad, expected_root=snap.merkle_root)


def test_inclusion_invalid_index_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    proof = plhc.prove_inclusion(snap, snap.leaves[0].leaf_id)
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=999,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=proof.siblings,
        root=proof.root,
    )
    assert not plhc.verify_inclusion(bad)


def test_inclusion_invalid_tree_size_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    proof = plhc.prove_inclusion(snap, snap.leaves[0].leaf_id)
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=0,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=0,
        siblings=proof.siblings,
        root=proof.root,
    )
    assert not plhc.verify_inclusion(bad)


def test_odd_leaf_count_and_single_leaf():
    # single event+artifact → multiple leaves; force single leaf tree via builder
    from agenttrust.integrity.leaves import EvidenceLeaf

    one = EvidenceLeaf(
        leaf_id="event:only",
        kind="event",
        payload={"event_id": "only"},
        content_hash="1" * 64,
    )
    tree = build_merkle_tree([one])
    assert tree.leaf_count == 1
    proof = prove_inclusion(tree, "event:only")
    assert verify_inclusion(proof)

    # odd count
    leaves = [
        EvidenceLeaf(leaf_id=f"event:e{i}", kind="event", payload={"i": i}, content_hash=f"{i:064x}")
        for i in range(3)
    ]
    tree3 = build_merkle_tree(leaves)
    for leaf in tree3.leaves:
        assert verify_inclusion(prove_inclusion(tree3, leaf.leaf_id))


def test_empty_tree_semantics():
    tree = build_merkle_tree([])
    assert tree.leaf_count == 0
    assert len(tree.root) == 64


def test_malformed_proof_side_fails():
    t = _simple_trace()
    snap = PLHC().build_snapshot(t)
    proof = PLHC().prove_inclusion(snap, snap.leaves[0].leaf_id)
    if not proof.siblings:
        pytest.skip("no siblings")
    sibs = list(proof.siblings)
    sibs[0] = ("X", sibs[0][1])
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=tuple(sibs),
        root=proof.root,
    )
    assert not verify_inclusion(bad)


# --- Checkpoints ---


def test_genesis_and_chain():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0, created_at="2024-01-01T00:00:00Z")
    assert c0.previous_checkpoint_hash == GENESIS_PREV_HASH
    ok, _ = verify_checkpoint_chain([c0])
    assert ok

    # second checkpoint with different created_at but same root still links
    c1 = plhc.create_checkpoint(
        snap, sequence_number=1, previous_checkpoint=c0, created_at="2024-01-02T00:00:00Z"
    )
    ok, _ = verify_checkpoint_chain([c0, c1])
    assert ok
    assert c0.checkpoint_hash != c1.checkpoint_hash  # created_at differs


def test_modified_checkpoint_root_fails():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    from agenttrust.integrity.checkpoint import IntegrityCheckpoint

    bad = IntegrityCheckpoint(
        sequence_number=c0.sequence_number,
        previous_checkpoint_hash=c0.previous_checkpoint_hash,
        merkle_root="f" * 64,
        leaf_count=c0.leaf_count,
        canonicalization_version=c0.canonicalization_version,
        hash_algorithm=c0.hash_algorithm,
        checkpoint_format_version=c0.checkpoint_format_version,
        created_at=c0.created_at,
        checkpoint_hash=c0.checkpoint_hash,  # stale hash
    )
    result = plhc.verify_against_checkpoint(t, bad)
    assert result.status == IntegrityStatus.CONTRADICTED


def test_broken_chain_and_reorder():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    c2 = plhc.create_checkpoint(snap, sequence_number=2, previous_checkpoint=c1)
    ok, _ = verify_checkpoint_chain([c0, c1, c2])
    assert ok
    # reorder
    result = plhc.verify_checkpoint_chain([c0, c2, c1])
    assert result.status == IntegrityStatus.CONTRADICTED
    # delete middle by skipping
    result = plhc.verify_checkpoint_chain([c0, c2])
    assert result.status == IntegrityStatus.CONTRADICTED


def test_missing_checkpoint_unavailable():
    result = PLHC().verify_checkpoint_chain([])
    assert result.status == IntegrityStatus.UNAVAILABLE


def test_created_at_affects_checkpoint_hash_not_root():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c_a = plhc.create_checkpoint(snap, sequence_number=0, created_at="t0")
    c_b = plhc.create_checkpoint(snap, sequence_number=0, created_at="t1")
    assert c_a.merkle_root == c_b.merkle_root
    assert c_a.checkpoint_hash != c_b.checkpoint_hash


# --- End-to-end ---


def test_untampered_verifies():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    result = plhc.verify_against_checkpoint(t, cp)
    assert result.status == IntegrityStatus.VERIFIED


def test_event_tampering_detected():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    d = t.events[0].to_public_dict()
    d["status"] = "failure"
    t2 = _load([d] + [e.to_public_dict() for e in t.events[1:]], [a.to_public_dict() for a in t.artifacts])
    result = plhc.verify_against_checkpoint(t2, cp)
    assert result.status == IntegrityStatus.CONTRADICTED


def test_artifact_tampering_detected():
    t = _simple_trace()
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t), sequence_number=0)
    arts = [a.to_public_dict() for a in t.artifacts]
    arts[0] = make_artifact(arts[0]["artifact_id"], "tampered-content")
    t2 = _load([e.to_public_dict() for e in t.events], arts)
    assert plhc.verify_against_checkpoint(t2, cp).status == IntegrityStatus.CONTRADICTED


def test_event_deletion_detected():
    t = _simple_trace()
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t), sequence_number=0)
    # keep only e1
    t2 = _load(
        [e.to_public_dict() for e in t.events if e.event_id == "e1"],
        [a.to_public_dict() for a in t.artifacts],
    )
    assert plhc.verify_against_checkpoint(t2, cp).status == IntegrityStatus.CONTRADICTED


def test_event_insertion_detected():
    t = _simple_trace()
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t), sequence_number=0)
    events = [e.to_public_dict() for e in t.events] + [
        make_event("e3", category="other")
    ]
    t2 = _load(events, [a.to_public_dict() for a in t.artifacts])
    assert plhc.verify_against_checkpoint(t2, cp).status == IntegrityStatus.CONTRADICTED


def test_artifact_substitution_detected():
    t = _simple_trace()
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t), sequence_number=0)
    arts = [make_artifact("a1", "different")]
    t2 = _load([e.to_public_dict() for e in t.events], arts)
    assert plhc.verify_against_checkpoint(t2, cp).status == IntegrityStatus.CONTRADICTED


def test_determinism_and_no_mutation():
    t = _simple_trace()
    fp = t.fingerprint()
    plhc = PLHC()
    a = plhc.build_snapshot(t)
    b = plhc.build_snapshot(t)
    assert a.merkle_root == b.merkle_root
    assert a.to_dict() == b.to_dict()
    assert t.fingerprint() == fp
    assert a.canonicalization_version == CANONICALIZATION_VERSION


def test_relationship_substitution_detected():
    arts = [make_artifact("a1")]
    t1 = _load(
        [make_event("e1", outputs=["a1"]), make_event("e2", deps=["e1"], inputs=["a1"])],
        arts,
    )
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t1), sequence_number=0)
    t2 = _load(
        [
            make_event("e1", outputs=["a1"]),
            make_event("e2", inputs=["a1"], observed_after_event_ids=["e1"]),
        ],
        arts,
    )
    assert plhc.verify_against_checkpoint(t2, cp).status == IntegrityStatus.CONTRADICTED


# --- Assurance integration ---


def test_assurance_no_plhc_unavailable():
    t = _simple_trace()
    profile = AssuranceProfileCalculator().compute(t)
    assert profile.dimensions["audit_integrity"].status == AssuranceStatus.UNAVAILABLE


def test_assurance_valid_plhc_verified():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    result = plhc.verify_against_checkpoint(t, cp)
    profile = AssuranceProfileCalculator().compute(t, plhc_result=result)
    assert profile.dimensions["audit_integrity"].status == AssuranceStatus.VERIFIED
    assert "immutab" not in profile.dimensions["audit_integrity"].explanation.lower()


def test_assurance_tampering_contradicted():
    t = _simple_trace()
    plhc = PLHC()
    cp = plhc.create_checkpoint(plhc.build_snapshot(t), sequence_number=0)
    d = t.events[0].to_public_dict()
    d["status"] = "timeout"
    t2 = _load([d] + [e.to_public_dict() for e in t.events[1:]], [a.to_public_dict() for a in t.artifacts])
    result = plhc.verify_against_checkpoint(t2, cp)
    profile = AssuranceProfileCalculator().compute(t2, plhc_result=result)
    assert profile.dimensions["audit_integrity"].status == AssuranceStatus.CONTRADICTED
    assert profile.overall_status == AssuranceStatus.CONTRADICTED


def test_assurance_broken_chain_contradicted():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    chain = plhc.verify_checkpoint_chain([c0, c1])
    assert chain.status == IntegrityStatus.VERIFIED
    broken = plhc.verify_checkpoint_chain([c1])  # non-genesis without link context as sole
    # single non-zero sequence fails genesis rules
    assert broken.status == IntegrityStatus.CONTRADICTED
    profile = AssuranceProfileCalculator().compute(t, plhc_result=broken)
    assert profile.dimensions["audit_integrity"].status == AssuranceStatus.CONTRADICTED
