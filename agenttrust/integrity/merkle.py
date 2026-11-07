"""
Deterministic binary Merkle tree (AgentTrust Merkle v1).

Construction (NOT claiming RFC 6962 compliance):
- Leaves ordered by ``leaf_id`` ascending.
- Leaf node hash = H(DS_MERKLE_LEAF || content_hash_hex).
- Internal node hash = H(DS_MERKLE_NODE || left_hex || b"|" || right_hex).
- Odd count at a level: the last hash is promoted unchanged (no self-hash).
- Empty tree root = H(DS_MERKLE_EMPTY).

Inclusion proofs list sibling steps from leaf toward root with side markers
``L``/``R`` (combine) or ``P`` (odd-level promote, no combine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agenttrust.integrity.hashing import empty_merkle_root, merkle_leaf_hash, merkle_node_hash
from agenttrust.integrity.leaves import EvidenceLeaf

MERKLE_FORMAT_VERSION = "agenttrust-merkle-v1"


class MerkleError(ValueError):
    """Malformed tree or proof."""


@dataclass(frozen=True)
class InclusionProof:
    leaf_id: str
    leaf_index: int
    leaf_content_hash: str
    leaf_count: int
    siblings: tuple[tuple[str, str], ...]  # (side, sibling_hash) side in {"L","R"}
    root: str
    merkle_format_version: str = MERKLE_FORMAT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf_id": self.leaf_id,
            "leaf_index": self.leaf_index,
            "leaf_content_hash": self.leaf_content_hash,
            "leaf_count": self.leaf_count,
            "siblings": [{"side": s, "hash": h} for s, h in self.siblings],
            "root": self.root,
            "merkle_format_version": self.merkle_format_version,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "InclusionProof":
        sibs = tuple((item["side"], item["hash"]) for item in d["siblings"])
        return InclusionProof(
            leaf_id=d["leaf_id"],
            leaf_index=int(d["leaf_index"]),
            leaf_content_hash=d["leaf_content_hash"],
            leaf_count=int(d["leaf_count"]),
            siblings=sibs,
            root=d["root"],
            merkle_format_version=d.get("merkle_format_version", MERKLE_FORMAT_VERSION),
        )


@dataclass
class MerkleTree:
    leaves: list[EvidenceLeaf]
    leaf_hashes: list[str]
    root: str
    leaf_index_by_id: dict[str, int] = field(default_factory=dict)
    merkle_format_version: str = MERKLE_FORMAT_VERSION

    @property
    def leaf_count(self) -> int:
        return len(self.leaves)

    def to_dict(self) -> dict[str, Any]:
        return {
            "merkle_format_version": self.merkle_format_version,
            "leaf_count": self.leaf_count,
            "root": self.root,
            "leaves": [leaf.to_dict() for leaf in self.leaves],
            "leaf_hashes": list(self.leaf_hashes),
        }


def build_merkle_tree(leaves: list[EvidenceLeaf]) -> MerkleTree:
    ordered = sorted(leaves, key=lambda leaf: leaf.leaf_id)
    ids = [leaf.leaf_id for leaf in ordered]
    if len(ids) != len(set(ids)):
        raise MerkleError("duplicate leaf_id")

    if not ordered:
        return MerkleTree(
            leaves=[],
            leaf_hashes=[],
            root=empty_merkle_root(),
            leaf_index_by_id={},
        )

    leaf_hashes = [merkle_leaf_hash(leaf.content_hash) for leaf in ordered]
    root = _compute_root(leaf_hashes)
    index = {leaf.leaf_id: i for i, leaf in enumerate(ordered)}
    return MerkleTree(
        leaves=ordered,
        leaf_hashes=leaf_hashes,
        root=root,
        leaf_index_by_id=index,
    )


def _compute_root(level: list[str]) -> str:
    if not level:
        return empty_merkle_root()
    while len(level) > 1:
        nxt: list[str] = []
        i = 0
        while i < len(level):
            if i + 1 == len(level):
                nxt.append(level[i])  # promote
            else:
                nxt.append(merkle_node_hash(level[i], level[i + 1]))
            i += 2
        level = nxt
    return level[0]


def prove_inclusion(tree: MerkleTree, leaf_id: str) -> InclusionProof:
    if leaf_id not in tree.leaf_index_by_id:
        raise MerkleError(f"unknown leaf_id: {leaf_id}")
    idx = tree.leaf_index_by_id[leaf_id]
    if tree.leaf_count == 0:
        raise MerkleError("empty tree has no inclusion proofs")

    siblings: list[tuple[str, str]] = []
    level = list(tree.leaf_hashes)
    index = idx
    while len(level) > 1:
        if index % 2 == 0:
            if index + 1 < len(level):
                siblings.append(("R", level[index + 1]))
            else:
                # Promoted alone — record explicit promote step so verifiers
                # advance the index without combining hashes.
                siblings.append(("P", ""))
        else:
            siblings.append(("L", level[index - 1]))
        nxt: list[str] = []
        i = 0
        while i < len(level):
            if i + 1 == len(level):
                nxt.append(level[i])
            else:
                nxt.append(merkle_node_hash(level[i], level[i + 1]))
            i += 2
        index //= 2
        level = nxt

    leaf = tree.leaves[idx]
    return InclusionProof(
        leaf_id=leaf_id,
        leaf_index=idx,
        leaf_content_hash=leaf.content_hash,
        leaf_count=tree.leaf_count,
        siblings=tuple(siblings),
        root=tree.root,
    )


def verify_inclusion(proof: InclusionProof, *, expected_root: Optional[str] = None) -> bool:
    """
    Verify inclusion proof. Returns True iff valid.

    Sibling side markers: ``L`` / ``R`` combine with a sibling hash; ``P`` means
    an odd-level promote (no combine). Fail closed on malformed proofs.
    """
    if proof.merkle_format_version != MERKLE_FORMAT_VERSION:
        return False
    if proof.leaf_count < 1:
        return False
    if proof.leaf_index < 0 or proof.leaf_index >= proof.leaf_count:
        return False
    if not isinstance(proof.leaf_content_hash, str) or len(proof.leaf_content_hash) != 64:
        return False
    root_target = expected_root if expected_root is not None else proof.root
    if not isinstance(root_target, str) or len(root_target) != 64:
        return False
    if proof.root != root_target:
        return False

    current = merkle_leaf_hash(proof.leaf_content_hash)
    index = proof.leaf_index

    for side, sibling in proof.siblings:
        if side == "P":
            if sibling not in ("", None):
                return False
            if index % 2 != 0:
                return False
            index //= 2
            continue
        if side not in ("L", "R"):
            return False
        if not isinstance(sibling, str) or len(sibling) != 64:
            return False
        if side == "L":
            if index % 2 == 0:
                return False
            current = merkle_node_hash(sibling, current)
        else:
            if index % 2 == 1:
                return False
            current = merkle_node_hash(current, sibling)
        index //= 2

    return current == root_target
