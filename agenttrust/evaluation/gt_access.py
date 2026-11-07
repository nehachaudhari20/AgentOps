"""Evaluation-only ground-truth accessors (never used by online baselines as inputs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence

from agenttrust.benchmark.dataset.attribution_reference import (
    ALIGNMENT_DISCLOSURE,
    AttributionReferenceGT,
    build_intervention_attribution_reference,
)
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth


def load_ground_truth(path: Path) -> BenchmarkGroundTruth:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BenchmarkGroundTruth.from_dict(data)


def agent_reference_for_outcome(
    gt: BenchmarkGroundTruth, outcome_id: str
) -> Optional[dict[str, float]]:
    """
    Structural equal-root reference (historically primary).

    Disclosure: structurally aligned with ConservedRPA α=0 — see ALIGNMENT_DISCLOSURE.
    """
    _ = ALIGNMENT_DISCLOSURE
    attr = gt.attribution_reference
    if attr is None:
        return None
    if isinstance(attr, dict):
        attr = AttributionReferenceGT.from_dict(attr)
    for o in attr.outcomes:
        if o.outcome_id == outcome_id:
            if getattr(o, "status", "defined") == "undefined":
                return None
            return dict(o.root_agent_allocations)
    return None


def intervention_agent_reference_for_outcome(
    gt: BenchmarkGroundTruth,
    outcome_id: str,
    *,
    events: Optional[Sequence[dict[str, Any]]] = None,
) -> Optional[dict[str, float]]:
    """
    Independent intervention-participation reference.

    Built from planted InterventionRecord.affected_event_ids + event agent ids.
    Returns None when undefined (no interventions / no identifiable agents).
    Never uses ConservedRPA/MFAV outputs.
    """
    # Prefer stored secondary reference if present
    stored = getattr(gt, "intervention_attribution_reference", None)
    if stored is None and isinstance(getattr(gt, "to_dict", None), object):
        # May live on raw dict side-channel in newer packages
        pass
    if events is None:
        # Reconstruct agent map only from interventions' affected events is insufficient
        # without event records — caller should pass public events.
        events = []
    ref = build_intervention_attribution_reference(
        list(events),
        [outcome_id],
        gt.interventions,
    )
    for o in ref.outcomes:
        if o.outcome_id == outcome_id:
            if o.status == "undefined" or not o.root_agent_allocations:
                return None
            return dict(o.root_agent_allocations)
    return None


def lineage_edge_sets(gt: BenchmarkGroundTruth) -> dict[str, set[tuple[str, str]]]:
    """
    Reference DEPENDS_ON / PRODUCES / CONSUMES edge sets from GT lineage.

    GT lineage is derived from the same simulator emission path as the graph
    (reconstruction fidelity), not an independently recorded production log.
    """
    depends: set[tuple[str, str]] = set()
    produces: set[tuple[str, str]] = set()
    consumes: set[tuple[str, str]] = set()
    for rel in gt.lineage.expected_relationships:
        rt = rel.get("rel_type")
        s, t = rel.get("source_id"), rel.get("target_id")
        if not s or not t:
            continue
        if rt == "DEPENDS_ON":
            depends.add((s, t))
        elif rt == "PRODUCES":
            produces.add((s, t))
        elif rt == "CONSUMES":
            consumes.add((s, t))
    return {"DEPENDS_ON": depends, "PRODUCES": produces, "CONSUMES": consumes}
