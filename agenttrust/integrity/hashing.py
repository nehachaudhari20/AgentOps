"""Domain-separated SHA-256 primitives for PLHC (Phase 2.7.1)."""

from __future__ import annotations

import hashlib
from typing import Union

from agenttrust.integrity.canonicalization import canonicalize

BytesLike = Union[bytes, bytearray, memoryview]

HASH_ALGORITHM = "sha256"
SUPPORTED_HASH_ALGORITHMS = frozenset({HASH_ALGORITHM})

# Domain separation tags (UTF-8). Changing a tag changes all dependent hashes.
DS_LEAF_EVENT = b"AT|LEAF|EVENT|v1|"
DS_LEAF_ARTIFACT = b"AT|LEAF|ARTIFACT|v1|"
DS_LEAF_RELATIONSHIP = b"AT|LEAF|RELATIONSHIP|v1|"

# Merkle v2: leaf hash binds leaf_id + content_hash
DS_MERKLE_LEAF = b"AT|MERKLE|LEAF|v2|"
DS_MERKLE_NODE = b"AT|MERKLE|NODE|v2|"
DS_MERKLE_EMPTY = b"AT|MERKLE|EMPTY|v2|"

# Checkpoint domain (payload includes merkle_format_version as of checkpoint-v2)
DS_CHECKPOINT = b"AT|CHECKPOINT|v1|"

# Historical v1 leaf domain (verification of old proofs is rejected, not reinterpreted)
DS_MERKLE_LEAF_V1 = b"AT|MERKLE|LEAF|v1|"


def sha256_hex(data: BytesLike) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def domain_hash(domain: bytes, *parts: BytesLike) -> str:
    """SHA-256 hex of domain || part0 || part1 || ..."""
    h = hashlib.sha256()
    h.update(domain)
    for p in parts:
        h.update(bytes(p))
    return h.hexdigest()


def leaf_content_hash(domain: bytes, canonical_payload: bytes) -> str:
    return domain_hash(domain, canonical_payload)


def merkle_leaf_hash(leaf_id: str, content_hash_hex: str) -> str:
    """
    Merkle leaf commitment (v2): binds stable leaf identity and content hash.

    Payload is canonical JSON ``{"content_hash": ..., "leaf_id": ...}``.
    """
    if not isinstance(leaf_id, str) or not leaf_id:
        raise ValueError("leaf_id must be a non-empty string")
    payload = canonicalize({"leaf_id": leaf_id, "content_hash": content_hash_hex})
    return domain_hash(DS_MERKLE_LEAF, payload)


def merkle_node_hash(left_hex: str, right_hex: str) -> str:
    return domain_hash(
        DS_MERKLE_NODE,
        left_hex.encode("ascii"),
        b"|",
        right_hex.encode("ascii"),
    )


def empty_merkle_root() -> str:
    return domain_hash(DS_MERKLE_EMPTY)


def checkpoint_hash(canonical_payload: bytes) -> str:
    return domain_hash(DS_CHECKPOINT, canonical_payload)
