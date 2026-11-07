"""
Attribution baselines for Phase 2.10 comparisons.

Online methods use only public events/artifacts via ProvenanceTrace.
Do not read ground-truth allocation vectors.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from itertools import combinations
from typing import Optional

import networkx as nx

from agenttrust.attribution.rpa import ConservedRPA, RPAConfig, RPAError
from agenttrust.evaluation.schema import AllocationResult, normalize_agent_vector
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.event import EventRecord

METHOD_VERSION = "2.10.0"


def _events_by_id(trace: ProvenanceTrace) -> dict[str, EventRecord]:
    return {e.event_id: e for e in trace.events}


def _ancestor_event_ids(graph: nx.DiGraph, outcome_id: str) -> set[str]:
    if outcome_id not in graph:
        return set()
    seen: set[str] = set()
    q: deque[str] = deque([outcome_id])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for p in graph.predecessors(cur):
            if p not in seen:
                q.append(p)
    return seen


def _agent_of(evmap: dict[str, EventRecord], eid: str) -> str:
    ev = evmap.get(eid)
    if ev is None or not ev.agent_id:
        return "UNIDENTIFIED"
    return str(ev.agent_id)


def _aggregate_nodes_to_agents(
    node_alloc: dict[str, float], evmap: dict[str, EventRecord]
) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for nid, mass in node_alloc.items():
        if abs(mass) < 1e-18:
            continue
        out[_agent_of(evmap, nid)] += float(mass)
    return dict(out)


def _failed(
    method_id: str,
    *,
    trace_id: str,
    outcome_id: str,
    reason: str,
    projection_kind: Optional[str] = None,
    budget: str = "online_evidence",
) -> AllocationResult:
    return AllocationResult(
        method_id=method_id,
        method_version=METHOD_VERSION,
        information_budget=budget,
        trace_id=trace_id,
        outcome_id=outcome_id,
        projection_kind=projection_kind,
        agent_allocations={},
        status="failed",
        errors=[reason],
    )


def allocate_rpa(
    trace: ProvenanceTrace,
    outcome_id: str,
    *,
    projection_kind: ProjectionKind,
    alpha: float = 0.0,
    allow_incomplete: bool = False,
    method_id: Optional[str] = None,
) -> AllocationResult:
    mid = method_id or (
        "rpa_p1" if projection_kind == ProjectionKind.P1_DIRECT else "rpa_p2"
    )
    tid = next((e.trace_id for e in trace.events if e.trace_id), "unknown")
    try:
        proj = trace.project(projection_kind)
        if outcome_id not in proj.graph:
            return AllocationResult(
                method_id=mid,
                method_version=METHOD_VERSION,
                information_budget="online_evidence",
                trace_id=tid,
                outcome_id=outcome_id,
                projection_kind=projection_kind.value,
                agent_allocations={},
                status="ineligible",
                eligibility={"outcome_in_projection": False},
            )
        rpa = ConservedRPA().allocate(
            proj,
            outcome_id,
            config=RPAConfig(alpha=alpha, allow_incomplete=allow_incomplete),
            completeness=trace.completeness(),
            provenance_fingerprint=trace.fingerprint(),
        )
        raw = _aggregate_nodes_to_agents(rpa.node_allocations, _events_by_id(trace))
        vec, st = normalize_agent_vector(raw)
        return AllocationResult(
            method_id=mid,
            method_version=METHOD_VERSION,
            information_budget="online_evidence",
            trace_id=tid,
            outcome_id=outcome_id,
            projection_kind=projection_kind.value,
            agent_allocations=vec,
            status=st,
            eligibility={"outcome_in_projection": True},
            config={"alpha": alpha, "allow_incomplete": allow_incomplete},
            warnings=list(rpa.warnings),
            reproducibility={"rpa_algorithm_version": rpa.algorithm_version},
        )
    except RPAError as exc:
        return AllocationResult(
            method_id=mid,
            method_version=METHOD_VERSION,
            information_budget="online_evidence",
            trace_id=tid,
            outcome_id=outcome_id,
            projection_kind=projection_kind.value,
            agent_allocations={},
            status="ineligible",
            errors=[str(exc)],
            eligibility={"rpa_error": True},
        )
    except Exception as exc:  # noqa: BLE001
        return _failed(mid, trace_id=tid, outcome_id=outcome_id, reason=str(exc), projection_kind=projection_kind.value)


def allocate_b0_uniform(
    trace: ProvenanceTrace,
    outcome_id: str,
    *,
    projection_kind: ProjectionKind = ProjectionKind.P1_DIRECT,
) -> AllocationResult:
    """Uniform over agents of ancestor events of the outcome (P1 by default)."""
    tid = next((e.trace_id for e in trace.events if e.trace_id), "unknown")
    mid = "B0_uniform_agent"
    try:
        proj = trace.project(projection_kind)
        anc = _ancestor_event_ids(proj.graph, outcome_id)
        if not anc:
            return AllocationResult(
                method_id=mid,
                method_version=METHOD_VERSION,
                information_budget="online_evidence",
                trace_id=tid,
                outcome_id=outcome_id,
                projection_kind=projection_kind.value,
                agent_allocations={},
                status="ineligible",
                eligibility={"ancestors": 0},
            )
        agents = sorted({_agent_of(_events_by_id(trace), eid) for eid in anc})
        raw = {a: 1.0 for a in agents}
        vec, st = normalize_agent_vector(raw)
        return AllocationResult(
            method_id=mid,
            method_version=METHOD_VERSION,
            information_budget="online_evidence",
            trace_id=tid,
            outcome_id=outcome_id,
            projection_kind=projection_kind.value,
            agent_allocations=vec,
            status=st,
            eligibility={"n_agents": len(agents), "n_ancestors": len(anc)},
            config={"eligible_rule": "agents_on_ancestor_events"},
        )
    except Exception as exc:  # noqa: BLE001
        return _failed(mid, trace_id=tid, outcome_id=outcome_id, reason=str(exc))


def allocate_b1_last_touch(
    trace: ProvenanceTrace,
    outcome_id: str,
    *,
    projection_kind: ProjectionKind = ProjectionKind.P1_DIRECT,
) -> AllocationResult:
    """
    Attribute all mass to the agent of the latest ancestor event of the outcome
    (excluding the outcome itself when possible). Tie-break: max event_id.
    """
    tid = next((e.trace_id for e in trace.events if e.trace_id), "unknown")
    mid = "B1_last_touch"
    try:
        proj = trace.project(projection_kind)
        anc = _ancestor_event_ids(proj.graph, outcome_id)
        candidates = [eid for eid in anc if eid != outcome_id] or sorted(anc)
        if not candidates:
            return AllocationResult(
                method_id=mid,
                method_version=METHOD_VERSION,
                information_budget="online_evidence",
                trace_id=tid,
                outcome_id=outcome_id,
                projection_kind=projection_kind.value,
                agent_allocations={},
                status="ineligible",
            )
        evmap = _events_by_id(trace)

        def sort_key(eid: str) -> tuple:
            ev = evmap.get(eid)
            ts = ev.ts_start.isoformat() if ev and ev.ts_start else ""
            return (ts, eid)

        chosen = max(candidates, key=sort_key)
        agent = _agent_of(evmap, chosen)
        vec, st = normalize_agent_vector({agent: 1.0})
        return AllocationResult(
            method_id=mid,
            method_version=METHOD_VERSION,
            information_budget="online_evidence",
            trace_id=tid,
            outcome_id=outcome_id,
            projection_kind=projection_kind.value,
            agent_allocations=vec,
            status=st,
            eligibility={"chosen_event_id": chosen},
            warnings=["Last-touch uses temporal order; not causal proof."],
            config={"tie_break": "max_ts_start then max_event_id"},
        )
    except Exception as exc:  # noqa: BLE001
        return _failed(mid, trace_id=tid, outcome_id=outcome_id, reason=str(exc))


def allocate_b2_p1_equal_share(trace: ProvenanceTrace, outcome_id: str) -> AllocationResult:
    """Alias of RPA P1 α=0 — documented non-independent comparator."""
    res = allocate_rpa(
        trace,
        outcome_id,
        projection_kind=ProjectionKind.P1_DIRECT,
        alpha=0.0,
        method_id="B2_p1_equal_share",
    )
    res.information_budget = "alias"
    res.warnings = list(res.warnings) + [
        "B2 is mathematically ConservedRPA α=0 on P1; not an independent baseline."
    ]
    return res


def _outcome_reachable(graph: nx.DiGraph, keep_nodes: set[str], outcome_id: str) -> bool:
    if outcome_id not in keep_nodes:
        return False
    # Any path from a root (in-degree 0 in induced subgraph) or simply: outcome in component
    # Reachability: BFS predecessors within keep_nodes — outcome is "supported" if it has
    # a root ancestor chain inside keep, OR is itself a singleton root.
    sub = graph.subgraph(keep_nodes).copy()
    if outcome_id not in sub:
        return False
    # Walk ancestors within subgraph; if we can reach a node with no in-edge in subgraph, ok
    seen: set[str] = set()
    q: deque[str] = deque([outcome_id])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        preds = list(sub.predecessors(cur))
        if not preds:
            return True
        for p in preds:
            if p not in seen:
                q.append(p)
    return False


def allocate_b4_shapley(
    trace: ProvenanceTrace,
    outcome_id: str,
    *,
    projection_kind: ProjectionKind = ProjectionKind.P1_DIRECT,
    max_exact_agents: int = 12,
    n_samples: int = 2000,
    seed: int = 0,
) -> AllocationResult:
    """
    Offline combinatorial Shapley over agents.

    v(S)=1 iff outcome remains reachable retaining only events with agent_id in S.
    Exact for |A|<=max_exact_agents; else Monte Carlo permutation sampling.
    """
    tid = next((e.trace_id for e in trace.events if e.trace_id), "unknown")
    mid = "B4_shapley"
    try:
        proj = trace.project(projection_kind)
        if outcome_id not in proj.graph:
            return AllocationResult(
                method_id=mid,
                method_version=METHOD_VERSION,
                information_budget="offline_combinatorial",
                trace_id=tid,
                outcome_id=outcome_id,
                projection_kind=projection_kind.value,
                agent_allocations={},
                status="ineligible",
            )
        evmap = _events_by_id(trace)
        anc = _ancestor_event_ids(proj.graph, outcome_id)
        agents = sorted({_agent_of(evmap, eid) for eid in anc})
        if not agents:
            return AllocationResult(
                method_id=mid,
                method_version=METHOD_VERSION,
                information_budget="offline_combinatorial",
                trace_id=tid,
                outcome_id=outcome_id,
                projection_kind=projection_kind.value,
                agent_allocations={},
                status="undefined",
            )

        def events_for(agent_set: set[str]) -> set[str]:
            return {eid for eid in anc if _agent_of(evmap, eid) in agent_set}

        def v(agent_set: set[str]) -> float:
            keep = events_for(agent_set)
            return 1.0 if _outcome_reachable(proj.graph, keep, outcome_id) else 0.0

        phi: dict[str, float] = {a: 0.0 for a in agents}
        mode = "exact"
        approx_note = None
        if len(agents) <= max_exact_agents:
            n = len(agents)
            for r in range(n):
                for S in combinations(agents, r):
                    Sset = set(S)
                    for a in agents:
                        if a in Sset:
                            continue
                        phi[a] += (v(Sset | {a}) - v(Sset)) * (
                            1.0 / (math.comb(n - 1, r) * n)
                        )
        else:
            mode = "monte_carlo"
            rng = random.Random(int(seed))
            for _ in range(n_samples):
                order = agents[:]
                rng.shuffle(order)
                pref: set[str] = set()
                prev = 0.0
                for a in order:
                    pref.add(a)
                    cur = v(pref)
                    phi[a] += cur - prev
                    prev = cur
            for a in agents:
                phi[a] /= float(n_samples)
            approx_note = f"Monte Carlo n_samples={n_samples}; not exact."

        vec, st = normalize_agent_vector(phi)
        # Shapley values for this game sum to v(N)-v({}) which is 0 or 1
        return AllocationResult(
            method_id=mid,
            method_version=METHOD_VERSION,
            information_budget="offline_combinatorial",
            trace_id=tid,
            outcome_id=outcome_id,
            projection_kind=projection_kind.value,
            agent_allocations=vec,
            status=st if st == "ok" else ("undefined" if sum(phi.values()) <= 0 else st),
            eligibility={"n_agents": len(agents), "mode": mode},
            config={
                "max_exact_agents": max_exact_agents,
                "n_samples": n_samples,
                "seed": seed,
                "value_function": "reachability_agent_coalition.v1",
            },
            warnings=[
                "Shapley reachability game is offline combinatorial comparison, not causal credit.",
            ]
            + ([approx_note] if approx_note else []),
        )
    except Exception as exc:  # noqa: BLE001
        return _failed(
            mid,
            trace_id=tid,
            outcome_id=outcome_id,
            reason=str(exc),
            budget="offline_combinatorial",
        )


MARKOV_STATUS = {
    "method_id": "B3_markov",
    "status": "not_implemented_independent",
    "reason": (
        "Equal-parent reverse absorbing Markov flow on the attribution DAG is identical "
        "to ConservedRPA with alpha=0; no distinct defensible transition model is available."
    ),
}


def run_online_suite(
    trace: ProvenanceTrace,
    outcome_id: str,
    *,
    include_shapley: bool = False,
    shapley_seed: int = 0,
) -> list[AllocationResult]:
    results = [
        allocate_rpa(trace, outcome_id, projection_kind=ProjectionKind.P1_DIRECT),
        allocate_rpa(trace, outcome_id, projection_kind=ProjectionKind.P2_ARTIFACT_BRIDGE),
        allocate_b0_uniform(trace, outcome_id),
        allocate_b1_last_touch(trace, outcome_id),
        allocate_b2_p1_equal_share(trace, outcome_id),
    ]
    if include_shapley:
        results.append(allocate_b4_shapley(trace, outcome_id, seed=shapley_seed))
    return results
