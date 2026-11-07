"""Central ProvenanceTrace API for AgentTrust Phase 2.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

import networkx as nx

from agenttrust.mlpg.graph_builder import MLPGBuilder, graph_fingerprint
from agenttrust.mlpg.projections import AttributionProjection, ProjectionKind, project_attribution_dag
from agenttrust.schema.artifact import ArtifactRecord
from agenttrust.schema.enums import EventCategory, NodeKind
from agenttrust.schema.event import EventRecord
from agenttrust.schema.relationship import RelationshipRecord
from agenttrust.validation.report import ValidationReport
from agenttrust.validation.validator import TraceValidator


@dataclass
class TraceCompleteness:
    incomplete: bool
    has_dependency_cycle: bool
    suitable_for_dag_attribution: bool
    missing_dependency_parents: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "incomplete": self.incomplete,
            "has_dependency_cycle": self.has_dependency_cycle,
            "suitable_for_dag_attribution": self.suitable_for_dag_attribution,
            "missing_dependency_parents": list(self.missing_dependency_parents),
        }


class ProvenanceTrace:
    """
    Load → validate → build typed MLPG → project attribution views.

    Does not compute responsibility, trust, or cryptographic integrity.
    Represents observable execution lineage only.
    """

    def __init__(self) -> None:
        self._events: list[EventRecord] = []
        self._artifacts: list[ArtifactRecord] = []
        self._relationships: list[RelationshipRecord] = []
        self._graph: Optional[nx.MultiDiGraph] = None
        self._report: Optional[ValidationReport] = None
        self._validator = TraceValidator()
        self._builder = MLPGBuilder()
        self._loaded = False

    def reset(self) -> None:
        """Clear internal state so repeated loads do not accumulate."""
        self._events = []
        self._artifacts = []
        self._relationships = []
        self._graph = None
        self._report = None
        self._loaded = False

    def load_records(
        self,
        events: Sequence[Mapping[str, Any]],
        artifacts: Sequence[Mapping[str, Any]] | None = None,
        relationships: Sequence[Mapping[str, Any]] | None = None,
        *,
        default_trace_id: Optional[str] = None,
        replace: bool = True,
    ) -> ValidationReport:
        """
        Validate and construct the provenance graph from record mappings.

        Input mappings are not mutated. By default ``replace=True`` resets prior state.
        """
        if replace:
            self.reset()
        elif self._loaded:
            raise RuntimeError(
                "ProvenanceTrace already loaded; call reset() or load_records(..., replace=True)."
            )

        # Deep-copy defensive snapshots so callers cannot mutate after load via shared dicts
        event_copies = [deepcopy(dict(e)) for e in events]
        artifact_copies = [deepcopy(dict(a)) for a in (artifacts or [])]
        rel_copies = [deepcopy(dict(r)) for r in (relationships or [])]

        events_out, arts_out, rels_out, report = self._validator.validate_trace(
            events=event_copies,
            artifacts=artifact_copies,
            relationships=rel_copies,
            default_trace_id=default_trace_id,
        )
        self._events = events_out
        self._artifacts = arts_out
        self._relationships = rels_out
        self._report = report
        self._graph = self._builder.build(events_out, arts_out, rels_out)
        self._loaded = True
        return report

    @property
    def graph(self) -> nx.MultiDiGraph:
        self._ensure_loaded()
        assert self._graph is not None
        return self._graph

    @property
    def validation_report(self) -> ValidationReport:
        self._ensure_loaded()
        assert self._report is not None
        return self._report

    @property
    def events(self) -> tuple[EventRecord, ...]:
        self._ensure_loaded()
        return tuple(self._events)

    @property
    def artifacts(self) -> tuple[ArtifactRecord, ...]:
        self._ensure_loaded()
        return tuple(self._artifacts)

    @property
    def relationships(self) -> tuple[RelationshipRecord, ...]:
        self._ensure_loaded()
        return tuple(self._relationships)

    def completeness(self) -> TraceCompleteness:
        self._ensure_loaded()
        assert self._report is not None
        r = self._report
        return TraceCompleteness(
            incomplete=r.incomplete,
            has_dependency_cycle=r.has_dependency_cycle,
            suitable_for_dag_attribution=r.suitable_for_dag_attribution,
            missing_dependency_parents=tuple(r.missing_dependency_parents),
        )

    def outcome_candidates(self) -> list[str]:
        """
        Identify candidate outcome EVENT ids without computing responsibility.

        Heuristic (documented): category == decision, else event_type == action.
        """
        self._ensure_loaded()
        out: list[str] = []
        for ev in sorted(self._events, key=lambda e: e.event_id):
            if ev.category == EventCategory.DECISION or ev.event_type == "action":
                out.append(ev.event_id)
        return out

    def project(self, kind: ProjectionKind | str) -> AttributionProjection:
        """Return P1 or P2 attribution projection; does not modify the provenance graph."""
        self._ensure_loaded()
        if isinstance(kind, str):
            kind = ProjectionKind(kind)
        assert self._graph is not None
        before = graph_fingerprint(self._graph)
        projection = project_attribution_dag(self._graph, kind)
        after = graph_fingerprint(self._graph)
        if before != after:
            raise RuntimeError("Projection mutated provenance graph (internal error).")
        return projection

    def fingerprint(self) -> str:
        self._ensure_loaded()
        assert self._graph is not None
        return graph_fingerprint(self._graph)

    def _ensure_loaded(self) -> None:
        if not self._loaded or self._graph is None or self._report is None:
            raise RuntimeError("ProvenanceTrace has no loaded data; call load_records first.")
