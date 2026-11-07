"""
End-to-end PLHC integrity builder and verifier.

Does not mutate ProvenanceTrace. Does not claim immutability or external trust.
"""

from __future__ import annotations

from typing import Optional, Sequence

from agenttrust.integrity.checkpoint import (
    IntegrityCheckpoint,
    create_checkpoint,
    verify_checkpoint,
    verify_checkpoint_chain,
)
from agenttrust.integrity.leaves import LeafConstructionError, build_all_leaves
from agenttrust.integrity.merkle import (
    InclusionProof,
    MerkleError,
    build_merkle_tree,
    prove_inclusion,
    verify_inclusion,
)
from agenttrust.integrity.result import (
    DEFAULT_LIMITATIONS,
    IntegritySnapshot,
    IntegrityStatus,
    IntegrityVerificationResult,
    snapshot_from_tree,
)
from agenttrust.provenance_trace import ProvenanceTrace


class PLHC:
    """Provenance-Linked Hash Chain builder/verifier."""

    def build_snapshot(self, trace: ProvenanceTrace) -> IntegritySnapshot:
        """Build deterministic evidence leaves + Merkle root from a loaded trace."""
        before = trace.fingerprint()
        leaves = build_all_leaves(trace.events, trace.artifacts, trace.relationships)
        tree = build_merkle_tree(leaves)
        snap = snapshot_from_tree(tree, provenance_fingerprint=before)
        after = trace.fingerprint()
        if before != after:
            raise RuntimeError("PLHC.build_snapshot mutated ProvenanceTrace")
        return snap

    def create_checkpoint(
        self,
        snapshot: IntegritySnapshot,
        *,
        sequence_number: int = 0,
        previous_checkpoint: Optional[IntegrityCheckpoint] = None,
        created_at: Optional[str] = None,
    ) -> IntegrityCheckpoint:
        return create_checkpoint(
            sequence_number=sequence_number,
            merkle_root=snapshot.merkle_root,
            leaf_count=snapshot.leaf_count,
            previous_checkpoint=previous_checkpoint,
            created_at=created_at,
        )

    def prove_inclusion(self, snapshot: IntegritySnapshot, leaf_id: str) -> InclusionProof:
        tree = build_merkle_tree(snapshot.leaves)
        if tree.root != snapshot.merkle_root:
            raise MerkleError("snapshot merkle_root does not match rebuilt tree")
        return prove_inclusion(tree, leaf_id)

    def verify_inclusion(
        self,
        proof: InclusionProof,
        *,
        expected_root: Optional[str] = None,
    ) -> bool:
        return verify_inclusion(proof, expected_root=expected_root)

    def verify_against_checkpoint(
        self,
        trace: ProvenanceTrace,
        checkpoint: IntegrityCheckpoint,
        *,
        previous_checkpoint: Optional[IntegrityCheckpoint] = None,
    ) -> IntegrityVerificationResult:
        """
        Rebuild snapshot from ``trace`` and compare to a retained checkpoint.

        Distinguishes verified / contradicted / unavailable / incomplete.
        """
        limitations = list(DEFAULT_LIMITATIONS)
        if checkpoint is None:
            return IntegrityVerificationResult(
                status=IntegrityStatus.UNAVAILABLE,
                explanation="No checkpoint provided.",
                limitations=limitations,
            )

        ok_cp, reason_cp = verify_checkpoint(checkpoint, previous=previous_checkpoint)
        if not ok_cp:
            return IntegrityVerificationResult(
                status=IntegrityStatus.CONTRADICTED,
                explanation=f"Checkpoint verification failed: {reason_cp}",
                checkpoint=checkpoint,
                diagnostics=[reason_cp],
                limitations=limitations,
            )

        try:
            snapshot = self.build_snapshot(trace)
        except LeafConstructionError as exc:
            return IntegrityVerificationResult(
                status=IntegrityStatus.CONTRADICTED,
                explanation=f"Leaf construction failed: {exc}",
                checkpoint=checkpoint,
                diagnostics=[str(exc)],
                limitations=limitations,
            )

        diags: list[str] = []
        if snapshot.merkle_root != checkpoint.merkle_root:
            diags.append(
                f"merkle_root mismatch rebuilt={snapshot.merkle_root} "
                f"checkpoint={checkpoint.merkle_root}"
            )
        if snapshot.leaf_count != checkpoint.leaf_count:
            diags.append(
                f"leaf_count mismatch rebuilt={snapshot.leaf_count} "
                f"checkpoint={checkpoint.leaf_count}"
            )

        if diags:
            return IntegrityVerificationResult(
                status=IntegrityStatus.CONTRADICTED,
                explanation="Rebuilt evidence conflicts with retained checkpoint.",
                snapshot=snapshot,
                checkpoint=checkpoint,
                diagnostics=diags,
                limitations=limitations,
            )

        return IntegrityVerificationResult(
            status=IntegrityStatus.VERIFIED,
            explanation="Rebuilt evidence matches retained checkpoint Merkle root and leaf count.",
            snapshot=snapshot,
            checkpoint=checkpoint,
            diagnostics=[],
            limitations=limitations,
        )

    def verify_checkpoint_chain(
        self,
        checkpoints: Sequence[IntegrityCheckpoint],
    ) -> IntegrityVerificationResult:
        if not checkpoints:
            return IntegrityVerificationResult(
                status=IntegrityStatus.UNAVAILABLE,
                explanation="Checkpoint chain is empty.",
                limitations=list(DEFAULT_LIMITATIONS),
            )
        ok, reason = verify_checkpoint_chain(checkpoints)
        if not ok:
            return IntegrityVerificationResult(
                status=IntegrityStatus.CONTRADICTED,
                explanation=f"Checkpoint chain verification failed: {reason}",
                checkpoint=checkpoints[-1],
                diagnostics=[reason],
                limitations=list(DEFAULT_LIMITATIONS),
            )
        return IntegrityVerificationResult(
            status=IntegrityStatus.VERIFIED,
            explanation=f"Checkpoint chain of length {len(checkpoints)} verified.",
            checkpoint=checkpoints[-1],
            limitations=list(DEFAULT_LIMITATIONS),
        )

    def verify_snapshot_match(
        self,
        rebuilt: IntegritySnapshot,
        retained: IntegritySnapshot,
    ) -> IntegrityVerificationResult:
        diags: list[str] = []
        if rebuilt.merkle_root != retained.merkle_root:
            diags.append("merkle_root mismatch")
        if rebuilt.leaf_count != retained.leaf_count:
            diags.append("leaf_count mismatch")
        rebuilt_ids = {leaf.leaf_id for leaf in rebuilt.leaves}
        retained_ids = {leaf.leaf_id for leaf in retained.leaves}
        missing = sorted(retained_ids - rebuilt_ids)
        extra = sorted(rebuilt_ids - retained_ids)
        if missing:
            diags.append(f"missing leaves: {missing[:8]}")
        if extra:
            diags.append(f"extra leaves: {extra[:8]}")
        if diags:
            status = (
                IntegrityStatus.INCOMPLETE
                if missing and not extra and rebuilt.merkle_root != retained.merkle_root
                else IntegrityStatus.CONTRADICTED
            )
            # Deletion/insertion that changes the root is contradicted; explicit
            # partial coverage without a conflicting retained root is incomplete.
            if missing and not extra:
                status = IntegrityStatus.CONTRADICTED  # evidence removed vs retained commitment
            return IntegrityVerificationResult(
                status=status,
                explanation="Snapshot mismatch against retained commitment.",
                snapshot=rebuilt,
                diagnostics=diags,
                limitations=list(DEFAULT_LIMITATIONS),
            )
        # Compare content hashes for shared IDs
        retained_by_id = {leaf.leaf_id: leaf for leaf in retained.leaves}
        for leaf in rebuilt.leaves:
            other = retained_by_id[leaf.leaf_id]
            if leaf.content_hash != other.content_hash:
                return IntegrityVerificationResult(
                    status=IntegrityStatus.CONTRADICTED,
                    explanation=f"Leaf content hash mismatch for {leaf.leaf_id}",
                    snapshot=rebuilt,
                    diagnostics=[f"content_hash differs: {leaf.leaf_id}"],
                    limitations=list(DEFAULT_LIMITATIONS),
                )
        return IntegrityVerificationResult(
            status=IntegrityStatus.VERIFIED,
            explanation="Snapshots match.",
            snapshot=rebuilt,
            limitations=list(DEFAULT_LIMITATIONS),
        )
