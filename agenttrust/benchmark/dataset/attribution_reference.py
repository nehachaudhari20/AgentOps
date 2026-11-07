"""
Independent attribution reference labels (Phase 2.9).

Equal mass over root ancestors of each outcome in the event dependency DAG
constructed from generator outputs — NOT ConservedRPA, NOT causal ground truth.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any

ATTRIBUTION_REFERENCE_METHOD = "equal_root_ancestor_mass.v1"
GROUND_TRUTH_VERSION = "gt-2.9.0"


@dataclass
class OutcomeAttributionReference:
    outcome_id: str
    root_event_allocations: dict[str, float]
    root_agent_allocations: dict[str, float]
    ancestor_event_ids: list[str]
    method: str = ATTRIBUTION_REFERENCE_METHOD
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttributionReferenceGT:
    """Evaluation-only reference package for responsibility-style scoring later."""

    ground_truth_version: str
    method: str
    outcomes: list[OutcomeAttributionReference]
    disclaimer: str = (
        "equal_root_ancestor_mass assigns structural share among dependency-DAG roots "
        "reachable to each outcome. It is NOT causal responsibility, NOT legal liability, "
        "and MUST NOT be derived by copying ConservedRPA/MFAV outputs."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ground_truth_version": self.ground_truth_version,
            "method": self.method,
            "disclaimer": self.disclaimer,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttributionReferenceGT":
        outcomes = [
            OutcomeAttributionReference(**o) if isinstance(o, dict) else o
            for o in data.get("outcomes", [])
        ]
        return cls(
            ground_truth_version=data.get("ground_truth_version", GROUND_TRUTH_VERSION),
            method=data.get("method", ATTRIBUTION_REFERENCE_METHOD),
            outcomes=outcomes,
            disclaimer=data.get("disclaimer", ""),
        )


def _ancestors(events_by_id: dict[str, dict[str, Any]], outcome_id: str) -> set[str]:
    if outcome_id not in events_by_id:
        return set()
    seen: set[str] = set()
    q: deque[str] = deque([outcome_id])
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        ev = events_by_id.get(cur)
        if not ev:
            continue
        for dep in ev.get("dependency_event_ids") or []:
            if dep in events_by_id and dep not in seen:
                q.append(dep)
    return seen


def _roots_in_subgraph(
    events_by_id: dict[str, dict[str, Any]], nodes: set[str]
) -> list[str]:
    roots: list[str] = []
    for nid in sorted(nodes):
        ev = events_by_id.get(nid)
        if not ev:
            continue
        deps = [d for d in (ev.get("dependency_event_ids") or []) if d in nodes]
        if not deps:
            roots.append(nid)
    return roots


def build_attribution_reference(
    events: list[dict[str, Any]],
    outcome_ids: list[str],
) -> AttributionReferenceGT:
    """
    Build independent reference allocations from event dependency structure.

    Does not import or call ConservedRPA / MFAV.
    """
    events_by_id = {e["event_id"]: e for e in events}
    outcomes: list[OutcomeAttributionReference] = []
    for oid in sorted(outcome_ids):
        anc = _ancestors(events_by_id, oid)
        roots = _roots_in_subgraph(events_by_id, anc)
        notes: list[str] = []
        if not roots:
            notes.append("No roots found; empty allocation.")
            outcomes.append(
                OutcomeAttributionReference(
                    outcome_id=oid,
                    root_event_allocations={},
                    root_agent_allocations={},
                    ancestor_event_ids=sorted(anc),
                    notes=notes,
                )
            )
            continue
        share = 1.0 / float(len(roots))
        root_alloc = {r: share for r in roots}
        agent_mass: dict[str, float] = defaultdict(float)
        for r in roots:
            agent = events_by_id[r].get("agent_id") or "UNIDENTIFIED"
            agent_mass[str(agent)] += share
        outcomes.append(
            OutcomeAttributionReference(
                outcome_id=oid,
                root_event_allocations=root_alloc,
                root_agent_allocations=dict(sorted(agent_mass.items())),
                ancestor_event_ids=sorted(anc),
                notes=notes
                + [
                    "Mass conserved over root events (sum=1 when roots non-empty).",
                    "Agent map aggregates root event shares; not causal credit.",
                ],
            )
        )
    return AttributionReferenceGT(
        ground_truth_version=GROUND_TRUTH_VERSION,
        method=ATTRIBUTION_REFERENCE_METHOD,
        outcomes=outcomes,
    )
