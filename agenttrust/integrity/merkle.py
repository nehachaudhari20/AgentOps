"""
Deterministic binary Merkle tree (AgentTrust Merkle v2).

Construction (NOT claiming RFC 6962 compliance):
- Leaves ordered by ``leaf_id`` ascending.
- Leaf hash = H(DS_MERKLE_LEAF_v2 || canonicalize({leaf_id, content_hash})).
- Internal node hash = H(DS_MERKLE_NODE_v2 || left || "|" || right).
- Odd count at a level: the last hash is promoted unchanged (no self-hash).
- Empty tree root = H(DS_MERKLE_EMPTY_v2).

Inclusion proofs list sibling steps from leaf toward root with side markers
``L``/``R`` (combine) or ``P`` (odd-level promote, no combine).

Verification reconstructs the exact expected step sequence from
``(leaf_index, leaf_count)`` and rejects extra/missing/wrong steps.
Unsupported Merkle format versions (including historical v1) are rejected —
never reinterpreted under v2 semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agenttrust.integrity.digests import DigestError, is_valid_sha256_hex, normalize_sha256_hex
from agenttrust.integrity.hashing import empty_merkle_root, merkle_leaf_hash, merkle_node_hash
from agenttrust.integrity.leaves import EvidenceLeaf

MERKLE_FORMAT_VERSION = "agenttrust-merkle-v2"
SUPPORTED_MERKLE_FORMATS = frozenset({MERKLE_FORMAT_VERSION})
# Historical — never verified under v2 construction
LEGACY_MERKLE_FORMAT_V1 = "agenttrust-merkle-v1"


class MerkleError(ValueError):
    """Malformed tree or proof."""


@dataclass(frozen=True)
class InclusionProof:
    leaf_id: str
    leaf_index: int
    leaf_content_hash: str
    leaf_count: int
    siblings: tuple[tuple[str, str], ...]  # (side, sibling_hash); side in {L,R,P}
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


def expected_proof_sides(leaf_index: int, leaf_count: int) -> list[str]:
    """
    Reconstruct the exact L/R/P sequence implied by AgentTrust Merkle v1/v2
    tree-width evolution for ``(leaf_index, leaf_count)``.
    """
    if leaf_count < 1:
        raise MerkleError("leaf_count must be >= 1")
    if leaf_index < 0 or leaf_index >= leaf_count:
        raise MerkleError("leaf_index out of range")
    sides: list[str] = []
    index = leaf_index
    width = leaf_count
    while width > 1:
        if index % 2 == 1:
            sides.append("L")
        elif index + 1 < width:
            sides.append("R")
        else:
            sides.append("P")
        index //= 2
        width = width // 2 + (width % 2)
    return sides


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

    for leaf in ordered:
        if not is_valid_sha256_hex(leaf.content_hash):
            raise MerkleError(f"malformed leaf content_hash for {leaf.leaf_id}")

    leaf_hashes = [
        merkle_leaf_hash(leaf.leaf_id, normalize_sha256_hex(leaf.content_hash))
        for leaf in ordered
    ]
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
    if tree.merkle_format_version not in SUPPORTED_MERKLE_FORMATS:
        raise MerkleError(f"unsupported merkle format: {tree.merkle_format_version}")
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
        leaf_content_hash=normalize_sha256_hex(leaf.content_hash),
        leaf_count=tree.leaf_count,
        siblings=tuple(siblings),
        root=tree.root,
        merkle_format_version=MERKLE_FORMAT_VERSION,
    )


def verify_inclusion(proof: InclusionProof, *, expected_root: Optional[str] = None) -> bool:
    """
    Structurally validate and recompute inclusion proof under Merkle v2.

    Fail closed on malformed proofs, wrong shape for ``leaf_count``, or
    unsupported format versions (including historical v1).
    """
    try:
        return _verify_inclusion_strict(proof, expected_root=expected_root)
    except (DigestError, MerkleError, TypeError, AttributeError, ValueError):
        return False


def _verify_inclusion_strict(
    proof: InclusionProof,
    *,
    expected_root: Optional[str],
) -> bool:
    if not isinstance(getattr(proof, "merkle_format_version", None), str):
        return False
    if proof.merkle_format_version == LEGACY_MERKLE_FORMAT_V1:
        # Explicit reject — do not reinterpret v1 under v2 leaf binding
        return False
    if proof.merkle_format_version not in SUPPORTED_MERKLE_FORMATS:
        return False
    if not isinstance(proof.leaf_id, str) or not proof.leaf_id:
        return False
    if not isinstance(proof.leaf_index, int) or isinstance(proof.leaf_index, bool):
        return False
    if not isinstance(proof.leaf_count, int) or isinstance(proof.leaf_count, bool):
        return False
    if proof.leaf_count < 1:
        return False
    if proof.leaf_index < 0 or proof.leaf_index >= proof.leaf_count:
        return False

    content = normalize_sha256_hex(proof.leaf_content_hash, field="leaf_content_hash")
    root_claimed = normalize_sha256_hex(proof.root, field="root")
    root_target = (
        normalize_sha256_hex(expected_root, field="expected_root")
        if expected_root is not None
        else root_claimed
    )
    if root_claimed != root_target:
        return False

    expected_sides = expected_proof_sides(proof.leaf_index, proof.leaf_count)
    if not isinstance(proof.siblings, (tuple, list)):
        return False
    if len(proof.siblings) != len(expected_sides):
        return False

    current = merkle_leaf_hash(proof.leaf_id, content)
    index = proof.leaf_index
    width = proof.leaf_count

    for step_i, (side, sibling) in enumerate(proof.siblings):
        if side != expected_sides[step_i]:
            return False
        # Reconstruct expected step from live width/index as a second check
        if index % 2 == 1:
            live = "L"
        elif index + 1 < width:
            live = "R"
        else:
            live = "P"
        if side != live:
            return False

        if side == "P":
            if sibling not in ("", None):
                return False
            index //= 2
            width = width // 2 + (width % 2)
            continue

        sib = normalize_sha256_hex(sibling, field="sibling")
        if side == "L":
            current = merkle_node_hash(sib, current)
        else:
            current = merkle_node_hash(current, sib)
        index //= 2
        width = width // 2 + (width % 2)

    if width != 1:
        return False
    return current == root_target
