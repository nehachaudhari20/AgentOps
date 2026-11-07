"""Linked integrity checkpoints for PLHC (Phase 2.7.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

from agenttrust.integrity.canonicalization import CANONICALIZATION_VERSION, canonicalize
from agenttrust.integrity.digests import DigestError, normalize_sha256_hex, require_nonneg_int
from agenttrust.integrity.hashing import (
    HASH_ALGORITHM,
    SUPPORTED_HASH_ALGORITHMS,
    checkpoint_hash,
)
from agenttrust.integrity.merkle import MERKLE_FORMAT_VERSION, SUPPORTED_MERKLE_FORMATS
from agenttrust.schema.event import parse_timestamp

CHECKPOINT_FORMAT_VERSION = "agenttrust-checkpoint-v2"
SUPPORTED_CHECKPOINT_FORMATS = frozenset({CHECKPOINT_FORMAT_VERSION})
SUPPORTED_CANONICALIZATION = frozenset({CANONICALIZATION_VERSION})
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
    merkle_format_version: str
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
            "merkle_format_version": self.merkle_format_version,
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
            "merkle_format_version": self.merkle_format_version,
            "created_at": self.created_at,
        }


class CheckpointError(ValueError):
    """Invalid checkpoint construction or verification input."""


def _validate_created_at(created_at: Optional[str]) -> Optional[str]:
    if created_at is None:
        return None
    if not isinstance(created_at, str) or not created_at.strip():
        raise CheckpointError("created_at must be a non-empty ISO-8601 string or None")
    # Reuse schema timestamp parser for consistent UTC contract
    dt: datetime = parse_timestamp(created_at, field_name="created_at")
    # Store normalized Z form for hashing stability when callers pass offsets
    from agenttrust.schema.event import format_timestamp

    return format_timestamp(dt)


def validate_checkpoint_fields(
    *,
    sequence_number: Any,
    previous_checkpoint_hash: Any,
    merkle_root: Any,
    leaf_count: Any,
    canonicalization_version: Any,
    hash_algorithm: Any,
    checkpoint_format_version: Any,
    merkle_format_version: Any,
    created_at: Any,
    checkpoint_hash_value: Any | None = None,
    require_hash: bool = False,
) -> dict[str, Any]:
    """Validate and normalize checkpoint fields. Raises CheckpointError/DigestError."""
    try:
        seq = require_nonneg_int(sequence_number, field="sequence_number")
        n_leaves = require_nonneg_int(leaf_count, field="leaf_count")
        root = normalize_sha256_hex(merkle_root, field="merkle_root")
    except DigestError as exc:
        raise CheckpointError(str(exc)) from exc

    if not isinstance(canonicalization_version, str):
        raise CheckpointError("canonicalization_version must be str")
    if canonicalization_version not in SUPPORTED_CANONICALIZATION:
        raise CheckpointError(f"unsupported canonicalization_version: {canonicalization_version}")

    if not isinstance(hash_algorithm, str):
        raise CheckpointError("hash_algorithm must be str")
    if hash_algorithm not in SUPPORTED_HASH_ALGORITHMS:
        raise CheckpointError(f"unsupported hash_algorithm: {hash_algorithm}")

    if not isinstance(checkpoint_format_version, str):
        raise CheckpointError("checkpoint_format_version must be str")
    if checkpoint_format_version not in SUPPORTED_CHECKPOINT_FORMATS:
        raise CheckpointError(
            f"unsupported checkpoint_format_version: {checkpoint_format_version}"
        )

    if not isinstance(merkle_format_version, str):
        raise CheckpointError("merkle_format_version must be str")
    if merkle_format_version not in SUPPORTED_MERKLE_FORMATS:
        raise CheckpointError(f"unsupported merkle_format_version: {merkle_format_version}")

    if not isinstance(previous_checkpoint_hash, str):
        raise CheckpointError("previous_checkpoint_hash must be str")
    if seq == 0:
        if previous_checkpoint_hash != GENESIS_PREV_HASH:
            raise CheckpointError("genesis previous_checkpoint_hash must be GENESIS")
        prev = GENESIS_PREV_HASH
    else:
        try:
            prev = normalize_sha256_hex(
                previous_checkpoint_hash, field="previous_checkpoint_hash"
            )
        except DigestError as exc:
            raise CheckpointError(str(exc)) from exc

    created = _validate_created_at(created_at)

    chash = None
    if require_hash or checkpoint_hash_value is not None:
        try:
            chash = normalize_sha256_hex(checkpoint_hash_value, field="checkpoint_hash")
        except DigestError as exc:
            raise CheckpointError(str(exc)) from exc

    return {
        "sequence_number": seq,
        "previous_checkpoint_hash": prev,
        "merkle_root": root,
        "leaf_count": n_leaves,
        "canonicalization_version": canonicalization_version,
        "hash_algorithm": hash_algorithm,
        "checkpoint_format_version": checkpoint_format_version,
        "merkle_format_version": merkle_format_version,
        "created_at": created,
        "checkpoint_hash": chash,
    }


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
    merkle_format_version: str = MERKLE_FORMAT_VERSION,
) -> IntegrityCheckpoint:
    if previous_checkpoint is None:
        if sequence_number != 0:
            raise CheckpointError("genesis checkpoint must have sequence_number 0")
        prev = GENESIS_PREV_HASH
    else:
        ok_self, reason_self = _verify_checkpoint_self(previous_checkpoint)
        if not ok_self:
            raise CheckpointError(f"previous checkpoint invalid: {reason_self}")
        if sequence_number != previous_checkpoint.sequence_number + 1:
            raise CheckpointError(
                f"sequence_number {sequence_number} is not contiguous after "
                f"{previous_checkpoint.sequence_number}"
            )
        prev = previous_checkpoint.checkpoint_hash

    fields = validate_checkpoint_fields(
        sequence_number=sequence_number,
        previous_checkpoint_hash=prev,
        merkle_root=merkle_root,
        leaf_count=leaf_count,
        canonicalization_version=canonicalization_version,
        hash_algorithm=hash_algorithm,
        checkpoint_format_version=checkpoint_format_version,
        merkle_format_version=merkle_format_version,
        created_at=created_at,
        require_hash=False,
    )

    provisional = IntegrityCheckpoint(
        sequence_number=fields["sequence_number"],
        previous_checkpoint_hash=fields["previous_checkpoint_hash"],
        merkle_root=fields["merkle_root"],
        leaf_count=fields["leaf_count"],
        canonicalization_version=fields["canonicalization_version"],
        hash_algorithm=fields["hash_algorithm"],
        checkpoint_format_version=fields["checkpoint_format_version"],
        merkle_format_version=fields["merkle_format_version"],
        created_at=fields["created_at"],
        checkpoint_hash="",
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
        merkle_format_version=provisional.merkle_format_version,
        created_at=provisional.created_at,
        checkpoint_hash=digest,
    )


def _verify_checkpoint_self(checkpoint: Any) -> tuple[bool, str]:
    try:
        fields = validate_checkpoint_fields(
            sequence_number=checkpoint.sequence_number,
            previous_checkpoint_hash=checkpoint.previous_checkpoint_hash,
            merkle_root=checkpoint.merkle_root,
            leaf_count=checkpoint.leaf_count,
            canonicalization_version=checkpoint.canonicalization_version,
            hash_algorithm=checkpoint.hash_algorithm,
            checkpoint_format_version=checkpoint.checkpoint_format_version,
            merkle_format_version=getattr(
                checkpoint, "merkle_format_version", MERKLE_FORMAT_VERSION
            ),
            created_at=checkpoint.created_at,
            checkpoint_hash_value=checkpoint.checkpoint_hash,
            require_hash=True,
        )
    except (CheckpointError, DigestError, AttributeError, TypeError) as exc:
        return False, str(exc)

    # Rebuild hash from normalized fields
    provisional = IntegrityCheckpoint(
        sequence_number=fields["sequence_number"],
        previous_checkpoint_hash=fields["previous_checkpoint_hash"],
        merkle_root=fields["merkle_root"],
        leaf_count=fields["leaf_count"],
        canonicalization_version=fields["canonicalization_version"],
        hash_algorithm=fields["hash_algorithm"],
        checkpoint_format_version=fields["checkpoint_format_version"],
        merkle_format_version=fields["merkle_format_version"],
        created_at=fields["created_at"],
        checkpoint_hash="",
    )
    expected = checkpoint_hash(canonicalize(provisional.payload_for_hash()))
    if expected != fields["checkpoint_hash"]:
        return False, "checkpoint_hash mismatch"
    return True, "ok"


def verify_checkpoint(
    checkpoint: Any,
    *,
    previous: Optional[Any] = None,
) -> tuple[bool, str]:
    """
    Verify checkpoint self-hash, field validity, and link to previous.

    Returns (ok, reason). Never raises for malformed objects.
    """
    try:
        ok, reason = _verify_checkpoint_self(checkpoint)
        if not ok:
            return False, reason

        if previous is None:
            if checkpoint.sequence_number != 0:
                return False, "non-genesis checkpoint without previous"
            if checkpoint.previous_checkpoint_hash != GENESIS_PREV_HASH:
                return False, "genesis previous_checkpoint_hash must be GENESIS"
            return True, "ok"

        ok_prev, reason_prev = _verify_checkpoint_self(previous)
        if not ok_prev:
            return False, f"previous invalid: {reason_prev}"
        if checkpoint.sequence_number != previous.sequence_number + 1:
            return False, "non-contiguous sequence_number"
        if checkpoint.previous_checkpoint_hash != previous.checkpoint_hash:
            return False, "previous_checkpoint_hash link broken"
        return True, "ok"
    except Exception as exc:  # fail closed
        return False, f"checkpoint verification error: {exc}"


def verify_checkpoint_chain(
    checkpoints: Sequence[Any],
) -> tuple[bool, str]:
    """
    Verify a supplied checkpoint prefix.

    A valid prefix proves integrity of the supplied sequence only — not that
    no later checkpoint exists.
    """
    try:
        if not checkpoints:
            return False, "empty checkpoint chain"
        ordered = list(checkpoints)
        ok, reason = verify_checkpoint(ordered[0], previous=None)
        if not ok:
            return False, f"checkpoint[0]: {reason}"
        if ordered[0].sequence_number != 0:
            return False, "checkpoint[0]: first checkpoint must be genesis (sequence 0)"
        for i in range(1, len(ordered)):
            ok, reason = verify_checkpoint(ordered[i], previous=ordered[i - 1])
            if not ok:
                return False, f"checkpoint[{i}]: {reason}"
        return True, "ok"
    except Exception as exc:
        return False, f"checkpoint chain error: {exc}"
