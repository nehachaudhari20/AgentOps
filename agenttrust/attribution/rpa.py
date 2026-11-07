"""
Conserved backward responsibility-flow allocation (Phase 2.2).

Structural allocation over event-only P1/P2 projections. Does not prove causality,
infer hidden model intent, or establish legal responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

import networkx as nx

from agenttrust.mlpg.projections import AttributionProjection, ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace, TraceCompleteness

ALGORITHM_NAME = "conserved_backward_flow"
ALGORITHM_VERSION = "2.2.0"


class ParentAllocationPolicy(str, Enum):
    """
    How a node's outbound flow is split among upstream parents.

    EQUAL_PARENTS: structural convention — equal share per parent edge.
    Not a measurement of causal influence or confidence.
    """

    EQUAL_PARENTS = "equal_parents"


@dataclass(frozen=True)
class RPAConfig:
    """Deterministic RPA configuration."""

    alpha: float = 0.0
    parent_policy: ParentAllocationPolicy = ParentAllocationPolicy.EQUAL_PARENTS
    allow_incomplete: bool = False
    # ConservedRPA requires a DAG. This flag does not enable cyclic propagation;
    # setting True still rejects cycles with an explicit unsupported error.
    allow_cycles: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= float(self.alpha) <= 1.0):
            raise ValueError(f"alpha must be in [0, 1], got {self.alpha}")


@dataclass
class RPAResult:
    outcome_id: str
    projection_kind: str
    algorithm_name: str
    algorithm_version: str
    alpha: float
    parent_allocation_policy: str
    node_allocations: dict[str, float]
    root_allocations: dict[str, float]
    conservation: dict[str, float]
    completeness: dict[str, Any]
    cycle_diagnostics: dict[str, Any]
    config: dict[str, Any]
    reproducibility: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    overridden_guards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "projection_kind": self.projection_kind,
            "algorithm_name": self.algorithm_name,
            "algorithm_version": self.algorithm_version,
            "alpha": self.alpha,
            "parent_allocation_policy": self.parent_allocation_policy,
            "node_allocations": dict(self.node_allocations),
            "root_allocations": dict(self.root_allocations),
            "conservation": dict(self.conservation),
            "completeness": dict(self.completeness),
            "cycle_diagnostics": dict(self.cycle_diagnostics),
            "config": dict(self.config),
            "reproducibility": dict(self.reproducibility),
            "warnings": list(self.warnings),
            "overridden_guards": list(self.overridden_guards),
        }


class RPAError(ValueError):
    """Raised when attribution cannot proceed under the selected guards."""


class ConservedRPA:
    """
    Per-outcome conserved backward flow with local retention parameter alpha.

    Baseline alpha=0: intermediate nodes retain no local share; mass is fully
    forwarded to parents and absorbed at roots (nodes with in-degree 0 in the
    attribution DAG, considering only paths relevant through the flow).

    Mathematical outline
    --------------------
    Let G=(V,E) be a DAG (event projection). Fix outcome o ∈ V.
    Maintain flow pot f(v) and allocation a(v).

    Initialise f(o)=1, f(v)=0 otherwise; a(v)=0 for all v.

    Process nodes in reverse topological order. For node v with current f(v):
      - If v has no parents in G: a(v) += f(v); f(v) ← 0  (root absorption)
      - Else:
          retain ← alpha * f(v);   a(v) += retain
          forward ← (1-alpha) * f(v)
          split forward among parents by parent_policy
          f(v) ← 0

    With alpha=0, a(v)=0 for all non-roots that only forward mass, and
    sum_v a(v) = sum_{roots that receive mass} a(r) = 1 when o is in G
    and G is a finite DAG with edges only among V.
    """

    def allocate(
        self,
        projection: AttributionProjection,
        outcome_id: str,
        *,
        config: Optional[RPAConfig] = None,
        completeness: Optional[TraceCompleteness] = None,
        provenance_fingerprint: Optional[str] = None,
    ) -> RPAResult:
        cfg = config or RPAConfig()
        warnings: list[str] = []
        overridden: list[str] = []

        graph = projection.graph
        if outcome_id not in graph:
            raise RPAError(f"Outcome {outcome_id!r} is not in the attribution projection.")

        # Completeness guard
        if completeness is not None and completeness.incomplete:
            if not cfg.allow_incomplete:
                raise RPAError(
                    "Trace is incomplete (missing dependency parents or artifacts); "
                    "refusing attribution. Pass allow_incomplete=True to override."
                )
            overridden.append("incomplete_trace")
            warnings.append("Attribution run with allow_incomplete=True on an incomplete trace.")

        # Cycle guard — cyclic propagation is not implemented
        cycle_info = self._cycle_diagnostics(graph)
        if cycle_info["has_cycle"]:
            if cfg.allow_cycles:
                raise RPAError(
                    "Attribution projection contains a cycle; ConservedRPA does not "
                    "support cyclic propagation (allow_cycles=True is not implemented). "
                    f"Cycle evidence: {cycle_info.get('cycle_nodes')}"
                )
            raise RPAError(
                "Attribution projection contains a cycle; DAG required. "
                f"Cycle evidence: {cycle_info.get('cycle_nodes')}"
            )

        node_alloc, root_alloc = self._propagate(graph, outcome_id, cfg)

        total = sum(node_alloc.values())
        root_total = sum(root_alloc.values())
        conservation = {
            "sum_node_allocations": total,
            "sum_root_allocations": root_total,
            "abs_error_from_one_nodes": abs(total - 1.0),
            "abs_error_from_one_roots": abs(root_total - 1.0),
        }

        completeness_dict = (
            completeness.to_dict()
            if completeness is not None
            else {"incomplete": None, "has_dependency_cycle": cycle_info["has_cycle"]}
        )

        return RPAResult(
            outcome_id=outcome_id,
            projection_kind=projection.kind.value,
            algorithm_name=ALGORITHM_NAME,
            algorithm_version=ALGORITHM_VERSION,
            alpha=float(cfg.alpha),
            parent_allocation_policy=cfg.parent_policy.value,
            node_allocations=node_alloc,
            root_allocations=root_alloc,
            conservation=conservation,
            completeness=completeness_dict,
            cycle_diagnostics=cycle_info,
            config={
                "alpha": float(cfg.alpha),
                "parent_policy": cfg.parent_policy.value,
                "allow_incomplete": cfg.allow_incomplete,
                "allow_cycles": cfg.allow_cycles,
            },
            reproducibility={
                "algorithm": ALGORITHM_NAME,
                "version": ALGORITHM_VERSION,
                "projection_kind": projection.kind.value,
                "outcome_id": outcome_id,
                "provenance_fingerprint": provenance_fingerprint,
                "n_projection_nodes": graph.number_of_nodes(),
                "n_projection_edges": graph.number_of_edges(),
            },
            warnings=warnings,
            overridden_guards=overridden,
        )

    def allocate_many(
        self,
        projection: AttributionProjection,
        outcome_ids: Sequence[str],
        *,
        config: Optional[RPAConfig] = None,
        completeness: Optional[TraceCompleteness] = None,
        provenance_fingerprint: Optional[str] = None,
    ) -> list[RPAResult]:
        """Independent per-outcome allocations (no cross-outcome aggregation)."""
        return [
            self.allocate(
                projection,
                oid,
                config=config,
                completeness=completeness,
                provenance_fingerprint=provenance_fingerprint,
            )
            for oid in outcome_ids
        ]

    def allocate_from_trace(
        self,
        trace: ProvenanceTrace,
        outcome_ids: Sequence[str] | None = None,
        *,
        projection_kind: ProjectionKind | str = ProjectionKind.P1_DIRECT,
        config: Optional[RPAConfig] = None,
    ) -> list[RPAResult]:
        """
        Convenience: project from a ProvenanceTrace then allocate.

        Does not modify the provenance graph.
        """
        if isinstance(projection_kind, str):
            projection_kind = ProjectionKind(projection_kind)
        before = trace.fingerprint()
        projection = trace.project(projection_kind)
        after = trace.fingerprint()
        if before != after:
            raise RuntimeError("Projection mutated provenance graph (internal error).")

        outcomes = list(outcome_ids) if outcome_ids is not None else trace.outcome_candidates()
        if not outcomes:
            raise RPAError("No outcome candidates provided or discovered.")

        return self.allocate_many(
            projection,
            outcomes,
            config=config,
            completeness=trace.completeness(),
            provenance_fingerprint=before,
        )

    def _propagate(
        self,
        graph: nx.DiGraph,
        outcome_id: str,
        cfg: RPAConfig,
    ) -> tuple[dict[str, float], dict[str, float]]:
        nodes = list(graph.nodes())
        flow = {n: 0.0 for n in nodes}
        alloc = {n: 0.0 for n in nodes}
        flow[outcome_id] = 1.0

        # Stable reverse topological order (tie-break by node id)
        try:
            topo = list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible as exc:
            raise RPAError("Projection is not a DAG.") from exc
        # Secondary sort within partial order: NetworkX topo is already valid;
        # for determinism across equivalent orders, sort by a priority that
        # respects edges: use lexicographic among nodes with same longest-path rank.
        rank = {n: 0 for n in nodes}
        for n in topo:
            for succ in graph.successors(n):
                rank[succ] = max(rank[succ], rank[n] + 1)
        reverse_order = sorted(nodes, key=lambda n: (-rank[n], n))

        alpha = float(cfg.alpha)

        for v in reverse_order:
            mass = flow[v]
            if mass == 0.0:
                continue
            parents = sorted(graph.predecessors(v))
            if not parents:
                alloc[v] += mass
                flow[v] = 0.0
                continue

            retain = alpha * mass
            forward = (1.0 - alpha) * mass
            alloc[v] += retain

            shares = self._parent_shares(parents, cfg.parent_policy)
            for p, share in shares.items():
                flow[p] += forward * share
            flow[v] = 0.0

        # Roots = nodes with in-degree 0
        roots = sorted(n for n in nodes if graph.in_degree(n) == 0)
        root_alloc = {r: alloc[r] for r in roots if alloc[r] != 0.0}
        # Include zero roots? Keep only non-zero for clarity; also expose all roots with zeros in node_allocations
        return alloc, root_alloc

    @staticmethod
    def _parent_shares(
        parents: Sequence[str],
        policy: ParentAllocationPolicy,
    ) -> dict[str, float]:
        if not parents:
            return {}
        if policy == ParentAllocationPolicy.EQUAL_PARENTS:
            w = 1.0 / len(parents)
            return {p: w for p in parents}
        raise ValueError(f"Unsupported parent policy: {policy}")

    @staticmethod
    def _cycle_diagnostics(graph: nx.DiGraph) -> dict[str, Any]:
        if nx.is_directed_acyclic_graph(graph):
            return {"has_cycle": False, "cycle_nodes": None}
        try:
            cycle_edges = list(nx.find_cycle(graph, orientation="original"))
            nodes: list[str] = []
            for item in cycle_edges:
                u, v = item[0], item[1]
                nodes.append(str(u))
            if cycle_edges:
                nodes.append(str(cycle_edges[0][0]))
            return {"has_cycle": True, "cycle_nodes": nodes, "cycle_edges": [(str(u), str(v)) for u, v, *_ in cycle_edges]}
        except nx.NetworkXNoCycle:
            return {"has_cycle": True, "cycle_nodes": None}
