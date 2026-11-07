"""Phase 2.7.1 PLHC cryptographic verification hardening tests."""

from __future__ import annotations

import pytest

from agenttrust import (
    AssuranceProfileCalculator,
    AssuranceStatus,
    IntegrityStatus,
    PLHC,
    ProvenanceTrace,
)
from agenttrust.assurance.dimensions import evaluate_audit_integrity
from agenttrust.integrity.checkpoint import (
    CHECKPOINT_FORMAT_VERSION,
    GENESIS_PREV_HASH,
    IntegrityCheckpoint,
    create_checkpoint,
    verify_checkpoint,
    verify_checkpoint_chain,
)
from agenttrust.integrity.digests import DigestError, normalize_sha256_hex
from agenttrust.integrity.hashing import HASH_ALGORITHM
from agenttrust.integrity.leaves import EvidenceLeaf
from agenttrust.integrity.merkle import (
    LEGACY_MERKLE_FORMAT_V1,
    MERKLE_FORMAT_VERSION,
    InclusionProof,
    build_merkle_tree,
    expected_proof_sides,
    prove_inclusion,
    verify_inclusion,
)
from agenttrust.integrity.result import IntegrityVerificationResult
from agenttrust.integrity.canonicalization import CANONICALIZATION_VERSION
from tests.conftest import make_artifact, make_event


def _simple_trace() -> ProvenanceTrace:
    arts = [make_artifact("a1", "payload-a")]
    events = [
        make_event("e1", category="reasoning", outputs=["a1"]),
        make_event("e2", category="decision", event_type="action", deps=["e1"], inputs=["a1"]),
    ]
    t = ProvenanceTrace()
    t.load_records(events, arts)
    return t


def _three_leaf_tree():
    leaves = [
        EvidenceLeaf(
            leaf_id=f"event:e{i}",
            kind="event",
            payload={"i": i},
            content_hash=f"{i:064x}",
        )
        for i in range(3)
    ]
    return build_merkle_tree(leaves)


# --- Digests ---


def test_digest_normalization():
    assert normalize_sha256_hex("A" * 64) == "a" * 64
    with pytest.raises(DigestError):
        normalize_sha256_hex("not-hex")
    with pytest.raises(DigestError):
        normalize_sha256_hex("a" * 63)
    with pytest.raises(DigestError):
        normalize_sha256_hex(123)


# --- Inclusion structural validation ---


def test_extra_promotion_step_rejected():
    tree = _three_leaf_tree()
    proof = prove_inclusion(tree, "event:e2")
    # e2 is last of 3 → expects a P then L; append an extra P
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=proof.siblings + (("P", ""),),
        root=proof.root,
        merkle_format_version=proof.merkle_format_version,
    )
    assert verify_inclusion(bad) is False


def test_missing_promotion_step_rejected():
    tree = _three_leaf_tree()
    proof = prove_inclusion(tree, "event:e2")
    assert "P" in [s for s, _ in proof.siblings]
    # Drop the P step
    sibs = tuple(s for s in proof.siblings if s[0] != "P")
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=sibs,
        root=proof.root,
    )
    assert verify_inclusion(bad) is False


def test_changed_leaf_id_fails():
    tree = _three_leaf_tree()
    proof = prove_inclusion(tree, "event:e0")
    bad = InclusionProof(
        leaf_id="event:forged",
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=proof.siblings,
        root=proof.root,
    )
    assert verify_inclusion(bad) is False


def test_legacy_v1_proof_rejected():
    tree = _three_leaf_tree()
    proof = prove_inclusion(tree, "event:e0")
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=proof.siblings,
        root=proof.root,
        merkle_format_version=LEGACY_MERKLE_FORMAT_V1,
    )
    assert verify_inclusion(bad) is False


def test_wrong_side_marker_fails():
    tree = _three_leaf_tree()
    proof = prove_inclusion(tree, "event:e0")
    # e0 should start with R; flip to L
    sibs = list(proof.siblings)
    side, h = sibs[0]
    sibs[0] = ("L" if side == "R" else "R", h)
    bad = InclusionProof(
        leaf_id=proof.leaf_id,
        leaf_index=proof.leaf_index,
        leaf_content_hash=proof.leaf_content_hash,
        leaf_count=proof.leaf_count,
        siblings=tuple(sibs),
        root=proof.root,
    )
    assert verify_inclusion(bad) is False


def test_expected_sides_match_generated_proofs():
    tree = _three_leaf_tree()
    for leaf in tree.leaves:
        proof = prove_inclusion(tree, leaf.leaf_id)
        expected = expected_proof_sides(proof.leaf_index, proof.leaf_count)
        assert [s for s, _ in proof.siblings] == expected
        assert verify_inclusion(proof)


def test_odd_leaf_every_index():
    tree = _three_leaf_tree()
    for leaf in tree.leaves:
        assert verify_inclusion(prove_inclusion(tree, leaf.leaf_id))


# --- Checkpoints ---


def test_checkpoint_binds_merkle_format():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    assert c0.merkle_format_version == MERKLE_FORMAT_VERSION
    assert "merkle_format_version" in c0.payload_for_hash()


def test_wrong_genesis_previous_hash_fails():
    t = _simple_trace()
    snap = PLHC().build_snapshot(t)
    c0 = PLHC().create_checkpoint(snap, sequence_number=0)
    bad = IntegrityCheckpoint(
        sequence_number=0,
        previous_checkpoint_hash="a" * 64,
        merkle_root=c0.merkle_root,
        leaf_count=c0.leaf_count,
        canonicalization_version=c0.canonicalization_version,
        hash_algorithm=c0.hash_algorithm,
        checkpoint_format_version=c0.checkpoint_format_version,
        merkle_format_version=c0.merkle_format_version,
        created_at=None,
        checkpoint_hash=c0.checkpoint_hash,
    )
    ok, reason = verify_checkpoint(bad, previous=None)
    assert not ok


@pytest.mark.parametrize("seq", [True, -1])
def test_bad_sequence_numbers_rejected_on_create(seq):
    with pytest.raises(Exception):
        create_checkpoint(
            sequence_number=seq,
            merkle_root="a" * 64,
            leaf_count=1,
            merkle_format_version=MERKLE_FORMAT_VERSION,
        )


@pytest.mark.parametrize("n", [True, -1])
def test_bad_leaf_counts_rejected_on_create(n):
    with pytest.raises(Exception):
        create_checkpoint(
            sequence_number=0,
            merkle_root="a" * 64,
            leaf_count=n,
            merkle_format_version=MERKLE_FORMAT_VERSION,
        )


def test_non_hex_root_rejected():
    with pytest.raises(Exception):
        create_checkpoint(
            sequence_number=0,
            merkle_root="zzzz" + "a" * 60,
            leaf_count=0,
            merkle_format_version=MERKLE_FORMAT_VERSION,
        )


def test_unsupported_algorithm_rejected():
    with pytest.raises(Exception):
        create_checkpoint(
            sequence_number=0,
            merkle_root="a" * 64,
            leaf_count=0,
            hash_algorithm="md5",
            merkle_format_version=MERKLE_FORMAT_VERSION,
        )


def test_unsupported_merkle_format_rejected():
    with pytest.raises(Exception):
        create_checkpoint(
            sequence_number=0,
            merkle_root="a" * 64,
            leaf_count=0,
            merkle_format_version=LEGACY_MERKLE_FORMAT_V1,
        )


def test_chain_prefix_not_complete_history_claim():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    result = plhc.verify_checkpoint_chain([c0, c1])
    assert result.status == IntegrityStatus.VERIFIED
    assert "later" in result.explanation.lower() or "prefix" in result.explanation.lower()


def test_deleted_middle_and_reorder():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    c2 = plhc.create_checkpoint(snap, sequence_number=2, previous_checkpoint=c1)
    ok, _ = verify_checkpoint_chain([c0, c2])
    assert not ok
    ok2, _ = verify_checkpoint_chain([c0, c2, c1])
    assert not ok2


def test_non_genesis_without_previous_fails_verify():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    ok, reason = verify_checkpoint(c1, previous=None)
    assert not ok


# --- Snapshot / checkpoint compatibility ---


def test_mismatched_merkle_format_on_verify():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    # Tamper format field while keeping old hash → self-hash fails first
    bad = IntegrityCheckpoint(
        sequence_number=c0.sequence_number,
        previous_checkpoint_hash=c0.previous_checkpoint_hash,
        merkle_root=c0.merkle_root,
        leaf_count=c0.leaf_count,
        canonicalization_version=c0.canonicalization_version,
        hash_algorithm=c0.hash_algorithm,
        checkpoint_format_version=c0.checkpoint_format_version,
        merkle_format_version=LEGACY_MERKLE_FORMAT_V1,
        created_at=c0.created_at,
        checkpoint_hash=c0.checkpoint_hash,
    )
    result = plhc.verify_against_checkpoint(t, bad)
    assert result.status == IntegrityStatus.CONTRADICTED


# --- Assurance hardening ---


def test_assurance_fake_verified_no_snapshot():
    fake = IntegrityVerificationResult(
        status=IntegrityStatus.VERIFIED,
        explanation="forged",
        snapshot=None,
        checkpoint=None,
    )
    dim = evaluate_audit_integrity(fake)
    assert dim.status != AssuranceStatus.VERIFIED


def test_assurance_fake_verified_malformed_root():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    # Mutate snapshot root to garbage while claiming verified
    snap.merkle_root = "not-a-digest"
    fake = IntegrityVerificationResult(
        status=IntegrityStatus.VERIFIED,
        explanation="forged",
        snapshot=snap,
        checkpoint=cp,
        checkpoint_link_verified=True,
    )
    dim = evaluate_audit_integrity(fake)
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_assurance_altered_leaves_contradicted():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    # Tamper a leaf content hash without updating root
    snap.leaves[0] = EvidenceLeaf(
        leaf_id=snap.leaves[0].leaf_id,
        kind=snap.leaves[0].kind,
        payload=snap.leaves[0].payload,
        content_hash="f" * 64,
    )
    fake = IntegrityVerificationResult(
        status=IntegrityStatus.VERIFIED,
        explanation="forged",
        snapshot=snap,
        checkpoint=cp,
        checkpoint_link_verified=True,
    )
    dim = evaluate_audit_integrity(fake)
    assert dim.status == AssuranceStatus.CONTRADICTED


def test_assurance_nongenesis_without_pred_incomplete():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    c0 = plhc.create_checkpoint(snap, sequence_number=0)
    c1 = plhc.create_checkpoint(snap, sequence_number=1, previous_checkpoint=c0)
    fake = IntegrityVerificationResult(
        status=IntegrityStatus.VERIFIED,
        explanation="forged",
        snapshot=snap,
        checkpoint=c1,
        previous_checkpoint=None,
        checkpoint_link_verified=False,
    )
    dim = evaluate_audit_integrity(fake)
    assert dim.status in (AssuranceStatus.INCOMPLETE, AssuranceStatus.CONTRADICTED)
    assert dim.status != AssuranceStatus.VERIFIED


def test_assurance_valid_genesis_verified():
    t = _simple_trace()
    plhc = PLHC()
    snap = plhc.build_snapshot(t)
    cp = plhc.create_checkpoint(snap, sequence_number=0)
    result = plhc.verify_against_checkpoint(t, cp)
    assert result.status == IntegrityStatus.VERIFIED
    assert result.checkpoint_link_verified
    dim = evaluate_audit_integrity(result)
    assert dim.status == AssuranceStatus.VERIFIED
    profile = AssuranceProfileCalculator().compute(t, plhc_result=result)
    assert profile.dimensions["audit_integrity"].status == AssuranceStatus.VERIFIED


def test_assurance_status_passthrough_non_verified():
    for st, expected in [
        (IntegrityStatus.INCOMPLETE, AssuranceStatus.INCOMPLETE),
        (IntegrityStatus.UNAVAILABLE, AssuranceStatus.UNAVAILABLE),
        (IntegrityStatus.CONTRADICTED, AssuranceStatus.CONTRADICTED),
    ]:
        dim = evaluate_audit_integrity(
            IntegrityVerificationResult(status=st, explanation="x")
        )
        assert dim.status == expected
