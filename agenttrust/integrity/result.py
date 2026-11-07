"""Typed PLHC result and diagnostic structures (Phase 2.7.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from agenttrust.integrity.canonicalization import CANONICALIZATION_VERSION
from agenttrust.integrity.checkpoint import IntegrityCheckpoint
from agenttrust.integrity.hashing import HASH_ALGORITHM
from agenttrust.integrity.leaves import EvidenceLeaf
from agenttrust.integrity.merkle import MERKLE_FORMAT_VERSION, InclusionProof, MerkleTree


class IntegrityStatus(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"


@dataclass
class IntegritySnapshot:
    """Deterministic integrity snapshot over a ProvenanceTrace evidence set."""

    canonicalization_version: str
    hash_algorithm: str
    merkle_format_version: str
    leaves: list[EvidenceLeaf]
    merkle_root: str
    leaf_count: int
    leaf_index_by_id: dict[str, int]
    provenance_fingerprint: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": self.canonicalization_version,
            "hash_algorithm": self.hash_algorithm,
            "merkle_format_version": self.merkle_format_version,
            "merkle_root": self.merkle_root,
            "leaf_count": self.leaf_count,
            "leaf_index_by_id": dict(self.leaf_index_by_id),
            "leaves": [leaf.to_dict() for leaf in self.leaves],
            "provenance_fingerprint": self.provenance_fingerprint,
            "warnings": list(self.warnings),
        }


@dataclass
class IntegrityVerificationResult:
    status: IntegrityStatus
    explanation: str
    snapshot: Optional[IntegritySnapshot] = None
    checkpoint: Optional[IntegrityCheckpoint] = None
    previous_checkpoint: Optional[IntegrityCheckpoint] = None
    checkpoint_link_verified: bool = False
    diagnostics: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "explanation": self.explanation,
            "snapshot": None if self.snapshot is None else self.snapshot.to_dict(),
            "checkpoint": None if self.checkpoint is None else self.checkpoint.to_dict(),
            "previous_checkpoint": (
                None
                if self.previous_checkpoint is None
                else self.previous_checkpoint.to_dict()
            ),
            "checkpoint_link_verified": self.checkpoint_link_verified,
            "diagnostics": list(self.diagnostics),
            "limitations": list(self.limitations),
        }


DEFAULT_LIMITATIONS = [
    "PLHC is tamper-evident relative to a retained or independently trusted checkpoint; "
    "a local-only chain is not inherently immutable.",
    "PLHC does not prove that an event occurred, that artifact content is truthful, "
    "or that a relationship is causally valid.",
    "No external signature or anchoring is implemented in Phase 2.7 / 2.7.1.",
    "A verified checkpoint prefix proves integrity of the supplied sequence only, "
    "not that no later checkpoint exists.",
]


def snapshot_from_tree(
    tree: MerkleTree,
    *,
    provenance_fingerprint: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> IntegritySnapshot:
    return IntegritySnapshot(
        canonicalization_version=CANONICALIZATION_VERSION,
        hash_algorithm=HASH_ALGORITHM,
        merkle_format_version=MERKLE_FORMAT_VERSION,
        leaves=list(tree.leaves),
        merkle_root=tree.root,
        leaf_count=tree.leaf_count,
        leaf_index_by_id=dict(tree.leaf_index_by_id),
        provenance_fingerprint=provenance_fingerprint,
        warnings=list(warnings or []),
    )


__all__ = [
    "IntegrityStatus",
    "IntegritySnapshot",
    "IntegrityVerificationResult",
    "DEFAULT_LIMITATIONS",
    "snapshot_from_tree",
    "InclusionProof",
    "IntegrityCheckpoint",
]
