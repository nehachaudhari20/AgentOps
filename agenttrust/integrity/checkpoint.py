"""Linked integrity checkpoints for PLHC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from agenttrust.integrity.canonicalization import CANONICALIZATION_VERSION, canonicalize
from agenttrust.integrity.hashing import HASH_ALGORITHM, checkpoint_hash

CHECKPOINT_FORMAT_VERSION = "agenttrust-checkpoint-v1"
GENESIS_PREV_HASH = "GENESIS"


@dataclass(frozen=True)
class IntegrityCheckpoint:
    sequence_number: int
    previous_checkpoint_hash: str
    merkle_root: str
    leaf_count: int
    canonicalization_version: str
    hash_algorithm: str
    checkpoint_format_version: str
    created_at: Optional[str]  # explicit optional input; part of hash if present
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_number": self.sequence_number,
            "previous_checkpoint_hash": self.previous_checkpoint_hash,
            "merkle_root": self.merkle_root,
            "leaf_count": self.leaf_count,
            "canonicalization_version": self.canonicalization_version,
            "hash_algorithm": self.hash_algorithm,
            "checkpoint_format_version": self.checkpoint_format_version,
            "created_at": self.created_at,
            "checkpoint_hash": self.checkpoint_hash,
        }

    def payload_for_hash(self) -> dict[str, Any]:
        """Integrity-relevant fields bound into checkpoint_hash (excludes checkpoint_hash)."""
        return {
            "sequence_number": self.sequence_number,
            "previous_checkpoint_hash": self.previous_checkpoint_hash,
            "merkle_root": self.merkle_root,
            "leaf_count": self.leaf_count,
            "canonicalization_version": self.canonicalization_version,
            "hash_algorithm": self.hash_algorithm,
            "checkpoint_format_version": self.checkpoint_format_version,
            "created_at": self.created_at,
        }


class CheckpointError(ValueError):
    """Invalid checkpoint construction or verification input."""


def create_checkpoint(
    *,
    sequence_number: int,
    merkle_root: str,
    leaf_count: int,
    previous_checkpoint: Optional[IntegrityCheckpoint] = None,
    created_at: Optional[str] = None,
    canonicalization_version: str = CANONICALIZATION_VERSION,
    hash_algorithm: str = HASH_ALGORITHM,
    checkpoint_format_version: str = CHECKPOINT_FORMAT_VERSION,
) -> IntegrityCheckpoint:
    if sequence_number < 0:
        raise CheckpointError("sequence_number must be >= 0")
    if leaf_count < 0:
        raise CheckpointError("leaf_count must be >= 0")
    if not isinstance(merkle_root, str) or len(merkle_root) != 64:
        raise CheckpointError("merkle_root must be a 64-hex digest")

    if previous_checkpoint is None:
        if sequence_number != 0:
            raise CheckpointError("genesis checkpoint must have sequence_number 0")
        prev = GENESIS_PREV_HASH
    else:
        if sequence_number != previous_checkpoint.sequence_number + 1:
            raise CheckpointError(
                f"sequence_number {sequence_number} is not contiguous after "
                f"{previous_checkpoint.sequence_number}"
            )
        prev = previous_checkpoint.checkpoint_hash

    provisional = IntegrityCheckpoint(
        sequence_number=sequence_number,
        previous_checkpoint_hash=prev,
        merkle_root=merkle_root,
        leaf_count=leaf_count,
        canonicalization_version=canonicalization_version,
        hash_algorithm=hash_algorithm,
        checkpoint_format_version=checkpoint_format_version,
        created_at=created_at,
        checkpoint_hash="",  # filled below
    )
    digest = checkpoint_hash(canonicalize(provisional.payload_for_hash()))
    return IntegrityCheckpoint(
        sequence_number=provisional.sequence_number,
        previous_checkpoint_hash=provisional.previous_checkpoint_hash,
        merkle_root=provisional.merkle_root,
        leaf_count=provisional.leaf_count,
        canonicalization_version=provisional.canonicalization_version,
        hash_algorithm=provisional.hash_algorithm,
        checkpoint_format_version=provisional.checkpoint_format_version,
        created_at=provisional.created_at,
        checkpoint_hash=digest,
    )


def verify_checkpoint(
    checkpoint: IntegrityCheckpoint,
    *,
    previous: Optional[IntegrityCheckpoint] = None,
) -> tuple[bool, str]:
    """
    Verify checkpoint self-hash and link to previous.

    Returns (ok, reason).
    """
    expected = checkpoint_hash(canonicalize(checkpoint.payload_for_hash()))
    if expected != checkpoint.checkpoint_hash:
        return False, "checkpoint_hash mismatch"
    if previous is None:
        if checkpoint.sequence_number != 0:
            return False, "non-genesis checkpoint without previous"
        if checkpoint.previous_checkpoint_hash != GENESIS_PREV_HASH:
            return False, "genesis previous_checkpoint_hash must be GENESIS"
        return True, "ok"
    if checkpoint.sequence_number != previous.sequence_number + 1:
        return False, "non-contiguous sequence_number"
    if checkpoint.previous_checkpoint_hash != previous.checkpoint_hash:
        return False, "previous_checkpoint_hash link broken"
    return True, "ok"


def verify_checkpoint_chain(
    checkpoints: Sequence[IntegrityCheckpoint],
) -> tuple[bool, str]:
    if not checkpoints:
        return False, "empty checkpoint chain"
    ordered = list(checkpoints)
    ok, reason = verify_checkpoint(ordered[0], previous=None)
    if not ok:
        return False, f"checkpoint[0]: {reason}"
    for i in range(1, len(ordered)):
        ok, reason = verify_checkpoint(ordered[i], previous=ordered[i - 1])
        if not ok:
            return False, f"checkpoint[{i}]: {reason}"
    # Detect gaps if caller passed unsorted / non-start-at-zero sequences already covered
    return True, "ok"
