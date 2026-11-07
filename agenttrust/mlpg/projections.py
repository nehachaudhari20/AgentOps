"""Attribution DAG projections (P1/P2) — interface only, no responsibility scores."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import networkx as nx

from agenttrust.schema.enums import NodeKind, RelationshipType


class ProjectionKind(str, Enum):
    P1_DIRECT = "P1_DIRECT"
    P2_ARTIFACT_BRIDGE = "P2_ARTIFACT_BRIDGE"


@dataclass(frozen=True)
class ProjectedEdge:
    source_event_id: str
    target_event_id: str
    derived: bool
    evidence_path: tuple[str, ...]
    origin: str  # "DEPENDS_ON" or "ARTIFACT_BRIDGE"


@dataclass
class AttributionProjection:
    """Event-only DAG view for future RPA experiments."""

    kind: ProjectionKind
    graph: nx.DiGraph
    edges: list[ProjectedEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "n_nodes": self.graph.number_of_nodes(),
            "n_edges": self.graph.number_of_edges(),
            "edges": [
                {
                    "source": e.source_event_id,
                    "target": e.target_event_id,
                    "derived": e.derived,
                    "evidence_path": list(e.evidence_path),
                    "origin": e.origin,
                }
                for e in self.edges
            ],
        }


def project_attribution_dag(
    provenance_graph: nx.MultiDiGraph,
    kind: ProjectionKind,
) -> AttributionProjection:
    """
    Build an event-only attribution projection without mutating the provenance graph.

    P1: explicit DEPENDS_ON only.
    P2: P1 plus verified artifact bridges (PRODUCES then CONSUMES), deduplicated.
    """
    # Defensive: work on a structural copy of node attribute references is not needed;
    # we never modify provenance_graph.
    event_nodes = [
        n
        for n, d in provenance_graph.nodes(data=True)
        if d.get("node_kind") == NodeKind.EVENT.value
    ]
    out = nx.DiGraph()
    for n in sorted(event_nodes):
        # Copy attributes for convenience; projection does not own provenance.
        out.add_node(n, **dict(provenance_graph.nodes[n]))

    projected: dict[tuple[str, str], ProjectedEdge] = {}

    # Explicit DEPENDS_ON
    for u, v, key, data in provenance_graph.edges(keys=True, data=True):
        if data.get("rel_type") != RelationshipType.DEPENDS_ON.value:
            continue
        if data.get("derived", False):
            continue
        if u not in out or v not in out:
            continue
        pe = ProjectedEdge(
            source_event_id=u,
            target_event_id=v,
            derived=False,
            evidence_path=(u, v),
            origin="DEPENDS_ON",
        )
        projected[(u, v)] = pe

    if kind == ProjectionKind.P2_ARTIFACT_BRIDGE:
        # Map artifact -> producers / consumers from verified edges only
        producers: dict[str, list[str]] = {}
        consumers: dict[str, list[str]] = {}
        for u, v, key, data in provenance_graph.edges(keys=True, data=True):
            if data.get("derived", False):
                continue
            rel = data.get("rel_type")
            if rel == RelationshipType.PRODUCES.value:
                # event u → artifact v
                if provenance_graph.nodes[v].get("node_kind") != NodeKind.ARTIFACT.value:
                    continue
                if provenance_graph.nodes[v].get("content_hash") in (None, ""):
                    continue  # unverified / incomplete artifact
                producers.setdefault(v, []).append(u)
            elif rel == RelationshipType.CONSUMES.value:
                # artifact u → event v
                if provenance_graph.nodes[u].get("node_kind") != NodeKind.ARTIFACT.value:
                    continue
                if provenance_graph.nodes[u].get("content_hash") in (None, ""):
                    continue
                consumers.setdefault(u, []).append(v)

        for artifact_id, prod_events in producers.items():
            cons_events = consumers.get(artifact_id, [])
            for a in prod_events:
                for b in cons_events:
                    if a == b:
                        continue
                    if a not in out or b not in out:
                        continue
                    key = (a, b)
                    if key in projected:
                        # Already represented by explicit DEPENDS_ON — do not double-count
                        continue
                    projected[key] = ProjectedEdge(
                        source_event_id=a,
                        target_event_id=b,
                        derived=True,
                        evidence_path=(a, artifact_id, b),
                        origin="ARTIFACT_BRIDGE",
                    )

    for key in sorted(projected.keys()):
        pe = projected[key]
        out.add_edge(
            pe.source_event_id,
            pe.target_event_id,
            derived=pe.derived,
            origin=pe.origin,
            evidence_path=list(pe.evidence_path),
            # unweighted
        )

    edges = [projected[k] for k in sorted(projected.keys())]
    return AttributionProjection(kind=kind, graph=out, edges=edges)


def snapshot_edge_set(graph: nx.MultiDiGraph) -> set[tuple]:
    """Helper for tests: immutable edge identity snapshot."""
    return {
        (u, v, k, d.get("rel_type"), d.get("derived"), d.get("evidence"))
        for u, v, k, d in graph.edges(keys=True, data=True)
    }
