"""Deterministic unweighted EVENT+ARTIFACT graph construction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import networkx as nx

from agenttrust.schema.artifact import ArtifactRecord
from agenttrust.schema.enums import NodeKind
from agenttrust.schema.event import EventRecord, format_timestamp
from agenttrust.schema.relationship import RelationshipRecord


class MLPGBuilder:
    """
    Build a typed NetworkX MultiDiGraph from validated records.

    MultiDiGraph is required so distinct relationship types between the same
    endpoint pair (e.g. DEPENDS_ON and INVOKES) are preserved. Edges are
    keyed by ``rel_type`` and remain unweighted.
    """

    def build(
        self,
        events: list[EventRecord],
        artifacts: list[ArtifactRecord],
        relationships: list[RelationshipRecord],
    ) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()

        # Deterministic insertion: sort by id
        for art in sorted(artifacts, key=lambda a: a.artifact_id):
            graph.add_node(
                art.artifact_id,
                node_kind=NodeKind.ARTIFACT.value,
                artifact_type=art.artifact_type,
                content_hash=art.content_hash,
                schema_version=art.schema_version,
                storage_uri=art.storage_uri,
                metadata=dict(art.metadata),
            )

        for ev in sorted(events, key=lambda e: e.event_id):
            graph.add_node(
                ev.event_id,
                node_kind=NodeKind.EVENT.value,
                event_type=ev.event_type,
                category=ev.category.value,
                agent_id=ev.agent_id,
                status=ev.status.value,
                ts_start=format_timestamp(ev.ts_start),
                ts_end=format_timestamp(ev.ts_end),
                input_artifact_ids=list(ev.input_artifact_ids),
                output_artifact_ids=list(ev.output_artifact_ids),
                dependency_event_ids=list(ev.dependency_event_ids),
                schema_version=ev.schema_version,
                trace_id=ev.trace_id,
            )

        for rel in sorted(relationships, key=lambda r: r.edge_key()):
            if rel.source_id not in graph or rel.target_id not in graph:
                # Missing endpoints already flagged during validation.
                continue
            # Unweighted: do not set weight. Key by relationship type.
            graph.add_edge(
                rel.source_id,
                rel.target_id,
                key=rel.rel_type.value,
                rel_type=rel.rel_type.value,
                derived=rel.derived,
                evidence=rel.evidence,
            )

        return graph


def graph_fingerprint(graph: nx.MultiDiGraph) -> str:
    """Deterministic structural fingerprint for equivalence checks."""
    nodes = []
    for n in sorted(graph.nodes()):
        data = {k: graph.nodes[n][k] for k in sorted(graph.nodes[n])}
        nodes.append({"id": n, "data": data})
    edges = []
    edge_iter = graph.edges(keys=True, data=True)
    for u, v, k, d in sorted(edge_iter, key=lambda t: (t[0], t[1], t[2])):
        edges.append(
            {
                "source": u,
                "target": v,
                "key": k,
                "rel_type": d.get("rel_type"),
                "derived": d.get("derived", False),
                "evidence": d.get("evidence"),
            }
        )
    payload = json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def node_public_attrs(graph: nx.Graph, node_id: str) -> dict[str, Any]:
    return dict(graph.nodes[node_id])
