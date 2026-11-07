"""
Attribution reference labels (Phase 2.9 + 2.13 correction).

Methods
-------
equal_root_ancestor_mass.v1
    Structural equal mass over dependency-DAG roots reachable to an outcome.
    **Scientifically limited:** the primary RPA allocator with alpha=0 also
    concentrates mass at roots under equal-parent reverse flow. Agreement
    (MAE≈0) can reflect structural alignment rather than independently
    demonstrated attribution accuracy. Retained for historical comparison
    only; must be disclosed as aligned.

intervention_participation_mass.v1
    Equal mass over agents on planted InterventionRecord.affected_event_ids
    (simulator intervention semantics). Undefined when no interventions exist.
    Does NOT call the RPA/MFAV allocators. Not causal or legal responsibility.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

ATTRIBUTION_REFERENCE_METHOD = "equal_root_ancestor_mass.v1"
INTERVENTION_REFERENCE_METHOD = "intervention_participation_mass.v1"
GROUND_TRUTH_VERSION = "gt-2.13.0"

ALIGNMENT_DISCLOSURE = (
    "equal_root_ancestor_mass.v1 is structurally aligned with RPA alpha=0 "
    "(both place mass on dependency roots). Zero MAE against this reference is NOT "
    "independent proof of attribution accuracy."
)


@dataclass
class OutcomeAttributionReference:
    outcome_id: str
    root_event_allocations: dict[str, float]
    root_agent_allocations: dict[str, float]
    ancestor_event_ids: list[str]
    method: str = ATTRIBUTION_REFERENCE_METHOD
    status: str = "defined"  # defined | undefined
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttributionReferenceGT:
    """Evaluation-only reference package for responsibility-style scoring."""

    ground_truth_version: str
    method: str
    outcomes: list[OutcomeAttributionReference]
    disclaimer: str = (
        "Attribution references are synthetic structural or intervention labels. "
        "They are NOT causal responsibility and NOT legal liability. "
        + ALIGNMENT_DISCLOSURE
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ground_truth_version": self.ground_truth_version,
            "method": self.method,
            "disclaimer": self.disclaimer,
            "alignment_disclosure": ALIGNMENT_DISCLOSURE,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttributionReferenceGT":
        outcomes = []
        for o in data.get("outcomes", []):
            if isinstance(o, dict):
                outcomes.append(
                    OutcomeAttributionReference(
                        outcome_id=o["outcome_id"],
                        root_event_allocations=dict(o.get("root_event_allocations") or {}),
                        root_agent_allocations=dict(o.get("root_agent_allocations") or {}),
                        ancestor_event_ids=list(o.get("ancestor_event_ids") or []),
                        method=o.get("method", data.get("method", ATTRIBUTION_REFERENCE_METHOD)),
                        status=o.get("status", "defined"),
                        notes=list(o.get("notes") or []),
                    )
                )
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
    Structural equal-root reference (historically named 'independent').

    Does not import RPA/MFAV modules, but IS structurally aligned with RPA α=0.
    """
    events_by_id = {e["event_id"]: e for e in events}
    outcomes: list[OutcomeAttributionReference] = []
    for oid in sorted(outcome_ids):
        anc = _ancestors(events_by_id, oid)
        roots = _roots_in_subgraph(events_by_id, anc)
        notes = [ALIGNMENT_DISCLOSURE]
        if not roots:
            notes.append("No roots found; empty allocation.")
            outcomes.append(
                OutcomeAttributionReference(
                    outcome_id=oid,
                    root_event_allocations={},
                    root_agent_allocations={},
                    ancestor_event_ids=sorted(anc),
                    status="undefined",
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
                    "Not causal credit; structurally aligned with RPA alpha=0.",
                ],
            )
        )
    return AttributionReferenceGT(
        ground_truth_version=GROUND_TRUTH_VERSION,
        method=ATTRIBUTION_REFERENCE_METHOD,
        outcomes=outcomes,
    )


def build_intervention_attribution_reference(
    events: list[dict[str, Any]],
    outcome_ids: list[str],
    interventions: Sequence[Any],
) -> AttributionReferenceGT:
    """
    Equal mass over agents on planted intervention affected_event_ids.

    Undefined (status=undefined, empty vectors) when no interventions apply.
    Does not use RPA/MFAV outputs.
    """
    events_by_id = {e["event_id"]: e for e in events}
    # Collect agents from intervention records
    affected_agents: set[str] = set()
    affected_events: set[str] = set()
    for iv in interventions:
        eids = getattr(iv, "affected_event_ids", None)
        if eids is None and isinstance(iv, dict):
            eids = iv.get("affected_event_ids") or []
        for eid in eids or []:
            affected_events.add(str(eid))
            ev = events_by_id.get(str(eid))
            if ev and ev.get("agent_id"):
                affected_agents.add(str(ev["agent_id"]))
            elif not ev:
                # Event removed by incomplete_trace — still record UNIDENTIFIED slot? skip
                pass

    outcomes: list[OutcomeAttributionReference] = []
    for oid in sorted(outcome_ids):
        if not affected_agents:
            outcomes.append(
                OutcomeAttributionReference(
                    outcome_id=oid,
                    root_event_allocations={},
                    root_agent_allocations={},
                    ancestor_event_ids=sorted(affected_events),
                    method=INTERVENTION_REFERENCE_METHOD,
                    status="undefined",
                    notes=[
                        "No planted interventions / no identifiable affected agents; "
                        "intervention attribution undefined (not fabricated).",
                    ],
                )
            )
            continue
        share = 1.0 / float(len(affected_agents))
        agent_alloc = {a: share for a in sorted(affected_agents)}
        outcomes.append(
            OutcomeAttributionReference(
                outcome_id=oid,
                root_event_allocations={},  # event-level not claimed for this method
                root_agent_allocations=agent_alloc,
                ancestor_event_ids=sorted(affected_events),
                method=INTERVENTION_REFERENCE_METHOD,
                status="defined",
                notes=[
                    "Equal mass over agents on InterventionRecord.affected_event_ids.",
                    "Structural intervention participation — not causal/legal responsibility.",
                    "Independent of RPA/MFAV algorithm outputs.",
                ],
            )
        )
    return AttributionReferenceGT(
        ground_truth_version=GROUND_TRUTH_VERSION,
        method=INTERVENTION_REFERENCE_METHOD,
        outcomes=outcomes,
        disclaimer=(
            "intervention_participation_mass.v1 uses planted simulator interventions only. "
            "Not causal responsibility. Undefined when interventions are absent."
        ),
    )
