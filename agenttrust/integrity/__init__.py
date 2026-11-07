"""
Provenance-Linked Hash Chain (PLHC) — Phase 2.7.

Tamper-evident commitments over events, artifacts, and relationships.
Not immutability. Not causal proof. Not external anchoring.
"""

from agenttrust.integrity.canonicalization import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonicalize,
)
from agenttrust.integrity.checkpoint import (
    CHECKPOINT_FORMAT_VERSION,
    GENESIS_PREV_HASH,
    IntegrityCheckpoint,
    create_checkpoint,
    verify_checkpoint,
    verify_checkpoint_chain,
)
from agenttrust.integrity.hashing import HASH_ALGORITHM
from agenttrust.integrity.leaves import EvidenceLeaf, LeafConstructionError, build_all_leaves
from agenttrust.integrity.merkle import (
    MERKLE_FORMAT_VERSION,
    InclusionProof,
    MerkleError,
    MerkleTree,
    build_merkle_tree,
    prove_inclusion,
    verify_inclusion,
)
from agenttrust.integrity.result import (
    IntegritySnapshot,
    IntegrityStatus,
    IntegrityVerificationResult,
)
from agenttrust.integrity.verifier import PLHC

__all__ = [
    "PLHC",
    "CANONICALIZATION_VERSION",
    "CHECKPOINT_FORMAT_VERSION",
    "MERKLE_FORMAT_VERSION",
    "HASH_ALGORITHM",
    "GENESIS_PREV_HASH",
    "canonicalize",
    "CanonicalizationError",
    "EvidenceLeaf",
    "LeafConstructionError",
    "build_all_leaves",
    "MerkleTree",
    "MerkleError",
    "InclusionProof",
    "build_merkle_tree",
    "prove_inclusion",
    "verify_inclusion",
    "IntegrityCheckpoint",
    "create_checkpoint",
    "verify_checkpoint",
    "verify_checkpoint_chain",
    "IntegritySnapshot",
    "IntegrityStatus",
    "IntegrityVerificationResult",
]
