"""Property-style conservation tests for conserved RPA."""

from __future__ import annotations

import math
import random

import networkx as nx
import pytest

from agenttrust.attribution.rpa import ConservedRPA, RPAConfig
from agenttrust.mlpg.projections import AttributionProjection, ProjectionKind


def _random_dag(n: int, edge_prob: float, seed: int) -> nx.DiGraph:
    rng = random.Random(seed)
    nodes = [f"n{i:02d}" for i in range(n)]
    g = nx.DiGraph()
    g.add_nodes_from(nodes)
    for i, u in enumerate(nodes):
        for v in nodes[i + 1 :]:
            if rng.random() < edge_prob:
                g.add_edge(u, v)  # lower index -> higher: acyclic
    return g


@pytest.mark.parametrize("seed", list(range(20)))
@pytest.mark.parametrize("alpha", [0.0, 0.25, 0.5, 1.0])
def test_conservation_on_random_dags(seed: int, alpha: float):
    g = _random_dag(n=8, edge_prob=0.35, seed=seed)
    # Ensure at least one edge path by connecting chain if empty
    nodes = sorted(g.nodes())
    if g.number_of_edges() == 0:
        for i in range(len(nodes) - 1):
            g.add_edge(nodes[i], nodes[i + 1])
    outcome = nodes[-1]
    # Ensure outcome reachable from someone or is itself a root
    p = AttributionProjection(ProjectionKind.P1_DIRECT, g, [])
    r = ConservedRPA().allocate(p, outcome, config=RPAConfig(alpha=alpha))
    total = sum(r.node_allocations.values())
    assert math.isclose(total, 1.0, abs_tol=1e-12)
    assert all(v >= 0.0 and not math.isnan(v) for v in r.node_allocations.values())
    if alpha == 0.0:
        for n, v in r.node_allocations.items():
            if g.in_degree(n) > 0:
                assert math.isclose(v, 0.0, abs_tol=1e-12)
        assert math.isclose(sum(r.root_allocations.values()), 1.0, abs_tol=1e-12)
