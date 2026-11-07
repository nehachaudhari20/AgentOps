"""Domain-separated SHA-256 primitives for PLHC."""

from __future__ import annotations

import hashlib
from typing import Union

BytesLike = Union[bytes, bytearray, memoryview]

HASH_ALGORITHM = "sha256"

# Domain separation tags (UTF-8). Changing a tag changes all dependent hashes.
DS_LEAF_EVENT = b"AT|LEAF|EVENT|v1|"
DS_LEAF_ARTIFACT = b"AT|LEAF|ARTIFACT|v1|"
DS_LEAF_RELATIONSHIP = b"AT|LEAF|RELATIONSHIP|v1|"
DS_MERKLE_LEAF = b"AT|MERKLE|LEAF|v1|"
DS_MERKLE_NODE = b"AT|MERKLE|NODE|v1|"
DS_MERKLE_EMPTY = b"AT|MERKLE|EMPTY|v1|"
DS_CHECKPOINT = b"AT|CHECKPOINT|v1|"


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


def merkle_leaf_hash(content_hash_hex: str) -> str:
    return domain_hash(DS_MERKLE_LEAF, content_hash_hex.encode("ascii"))


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
