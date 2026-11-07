"""
Evidence leaf construction for events, artifacts, and relationships.

Excluded from commitments (intentionally):
- Artifact ``storage_uri`` (private / relocatable storage pointer)
- Raw artifact payloads
- Transient runtime objects
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from agenttrust.integrity.canonicalization import canonicalize
from agenttrust.integrity.hashing import (
    DS_LEAF_ARTIFACT,
    DS_LEAF_EVENT,
    DS_LEAF_RELATIONSHIP,
    leaf_content_hash,
)
from agenttrust.schema.artifact import ArtifactRecord
from agenttrust.schema.enums import RelationshipType
from agenttrust.schema.event import EventRecord, format_timestamp
from agenttrust.schema.relationship import RelationshipRecord

LEAF_KIND_EVENT = "event"
LEAF_KIND_ARTIFACT = "artifact"
LEAF_KIND_RELATIONSHIP = "relationship"

NS_EVENT = "EVENT"
NS_ARTIFACT = "ARTIFACT"


class LeafConstructionError(ValueError):
    """Raised when leaves cannot be built (e.g. duplicate IDs)."""


@dataclass(frozen=True)
class EvidenceLeaf:
    leaf_id: str
    kind: str
    payload: dict[str, Any]
    content_hash: str  # domain-separated hash of canonical payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf_id": self.leaf_id,
            "kind": self.kind,
            "payload": dict(self.payload),
            "content_hash": self.content_hash,
        }


def _rel_namespaces(rel_type: RelationshipType) -> tuple[str, str]:
    if rel_type in (
        RelationshipType.DEPENDS_ON,
        RelationshipType.INVOKES,
        RelationshipType.RETRIES,
        RelationshipType.OBSERVED_AFTER,
    ):
        return NS_EVENT, NS_EVENT
    if rel_type == RelationshipType.PRODUCES:
        return NS_EVENT, NS_ARTIFACT
    if rel_type == RelationshipType.CONSUMES:
        return NS_ARTIFACT, NS_EVENT
    raise LeafConstructionError(f"unknown relationship type: {rel_type}")


def event_payload(ev: EventRecord) -> dict[str, Any]:
    """Integrity-relevant event fields (actual schema names)."""
    return {
        "event_id": ev.event_id,
        "trace_id": ev.trace_id,
        "event_type": ev.event_type,
        "category": ev.category.value,
        "agent_id": ev.agent_id,
        "status": ev.status.value,
        "ts_start": format_timestamp(ev.ts_start),
        "ts_end": format_timestamp(ev.ts_end),
        "input_artifact_ids": list(ev.input_artifact_ids),
        "output_artifact_ids": list(ev.output_artifact_ids),
        "dependency_event_ids": list(ev.dependency_event_ids),
        "invokes_event_ids": list(ev.invokes_event_ids),
        "retries_event_id": ev.retries_event_id,
        "observed_after_event_ids": list(ev.observed_after_event_ids),
        "schema_version": ev.schema_version,
        "model_id": ev.model_id,
        "tool_id": ev.tool_id,
        # metadata as sorted list of pairs for deterministic array order
        "metadata": [[k, v] for k, v in sorted(ev.metadata, key=lambda p: p[0])],
    }


def artifact_payload(art: ArtifactRecord) -> dict[str, Any]:
    """
    Integrity-relevant artifact fields.

    Intentionally excludes ``storage_uri`` (private/relocatable pointer).
    """
    return {
        "artifact_id": art.artifact_id,
        "artifact_type": art.artifact_type,
        "content_hash": art.content_hash,
        "schema_version": art.schema_version,
        "metadata": [[k, v] for k, v in sorted(art.metadata, key=lambda p: p[0])],
    }


def relationship_payload(
    rel: RelationshipRecord,
    *,
    ordinal: int,
) -> dict[str, Any]:
    src_ns, tgt_ns = _rel_namespaces(rel.rel_type)
    return {
        "ordinal": ordinal,
        "rel_type": rel.rel_type.value,
        "source_namespace": src_ns,
        "source_id": rel.source_id,
        "target_namespace": tgt_ns,
        "target_id": rel.target_id,
        "derived": bool(rel.derived),
        "evidence": rel.evidence,
    }


def build_event_leaf(ev: EventRecord) -> EvidenceLeaf:
    payload = event_payload(ev)
    ch = leaf_content_hash(DS_LEAF_EVENT, canonicalize(payload))
    return EvidenceLeaf(
        leaf_id=f"event:{ev.event_id}",
        kind=LEAF_KIND_EVENT,
        payload=payload,
        content_hash=ch,
    )


def build_artifact_leaf(art: ArtifactRecord) -> EvidenceLeaf:
    payload = artifact_payload(art)
    ch = leaf_content_hash(DS_LEAF_ARTIFACT, canonicalize(payload))
    return EvidenceLeaf(
        leaf_id=f"artifact:{art.artifact_id}",
        kind=LEAF_KIND_ARTIFACT,
        payload=payload,
        content_hash=ch,
    )


def build_relationship_leaf(rel: RelationshipRecord, *, ordinal: int) -> EvidenceLeaf:
    payload = relationship_payload(rel, ordinal=ordinal)
    ch = leaf_content_hash(DS_LEAF_RELATIONSHIP, canonicalize(payload))
    # leaf_id includes ordinal so parallel same-type edges remain distinct
    leaf_id = (
        f"rel:{ordinal}:{rel.rel_type.value}:"
        f"{payload['source_namespace']}:{rel.source_id}:"
        f"{payload['target_namespace']}:{rel.target_id}"
    )
    return EvidenceLeaf(
        leaf_id=leaf_id,
        kind=LEAF_KIND_RELATIONSHIP,
        payload=payload,
        content_hash=ch,
    )


def build_all_leaves(
    events: tuple[EventRecord, ...] | list[EventRecord],
    artifacts: tuple[ArtifactRecord, ...] | list[ArtifactRecord],
    relationships: tuple[RelationshipRecord, ...] | list[RelationshipRecord],
) -> list[EvidenceLeaf]:
    """
    Build all evidence leaves with duplicate-ID rejection and stable ordering.

    Relationships are sorted by edge_key then assigned contiguous ordinals
    so multiplicity of distinct edges is preserved.
    """
    event_ids = [e.event_id for e in events]
    if len(event_ids) != len(set(event_ids)):
        raise LeafConstructionError("duplicate event_id in evidence set")
    art_ids = [a.artifact_id for a in artifacts]
    if len(art_ids) != len(set(art_ids)):
        raise LeafConstructionError("duplicate artifact_id in evidence set")

    leaves: list[EvidenceLeaf] = []
    for ev in sorted(events, key=lambda e: e.event_id):
        leaves.append(build_event_leaf(ev))
    for art in sorted(artifacts, key=lambda a: a.artifact_id):
        leaves.append(build_artifact_leaf(art))

    rels_sorted = sorted(
        relationships,
        key=lambda r: (r.rel_type.value, r.source_id, r.target_id, bool(r.derived), r.evidence or ""),
    )
    for i, rel in enumerate(rels_sorted):
        leaves.append(build_relationship_leaf(rel, ordinal=i))

    # Final stable order by leaf_id (independent of graph insertion order)
    leaves.sort(key=lambda leaf: leaf.leaf_id)
    leaf_ids = [leaf.leaf_id for leaf in leaves]
    if len(leaf_ids) != len(set(leaf_ids)):
        raise LeafConstructionError("duplicate leaf_id after construction")
    return leaves
