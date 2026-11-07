"""Evaluation-only ground-truth accessors (never used by online baselines as inputs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agenttrust.benchmark.dataset.attribution_reference import AttributionReferenceGT
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth


def load_ground_truth(path: Path) -> BenchmarkGroundTruth:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return BenchmarkGroundTruth.from_dict(data)


def agent_reference_for_outcome(
    gt: BenchmarkGroundTruth, outcome_id: str
) -> Optional[dict[str, float]]:
    attr = gt.attribution_reference
    if attr is None:
        return None
    if isinstance(attr, dict):
        attr = AttributionReferenceGT.from_dict(attr)
    for o in attr.outcomes:
        if o.outcome_id == outcome_id:
            return dict(o.root_agent_allocations)
    return None


def lineage_edge_sets(gt: BenchmarkGroundTruth) -> dict[str, set[tuple[str, str]]]:
    """Reference DEPENDS_ON / PRODUCES / CONSUMES edge sets from GT lineage."""
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
