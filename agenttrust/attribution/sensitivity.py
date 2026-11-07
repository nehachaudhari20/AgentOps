"""Sensitivity helpers for alternative alpha values (experimental configurations)."""

from __future__ import annotations

from typing import Iterable, Optional

from agenttrust.attribution.rpa import ConservedRPA, RPAConfig, RPAResult
from agenttrust.mlpg.projections import AttributionProjection
from agenttrust.provenance_trace import TraceCompleteness


def sweep_alpha(
    projection: AttributionProjection,
    outcome_id: str,
    alphas: Iterable[float],
    *,
    completeness: Optional[TraceCompleteness] = None,
    provenance_fingerprint: Optional[str] = None,
    allow_incomplete: bool = False,
) -> list[RPAResult]:
    """
    Run conserved RPA for multiple alpha values.

    Results for alpha != 0 are experimental configurations, not the approved baseline.
    """
    engine = ConservedRPA()
    results: list[RPAResult] = []
    for alpha in alphas:
        cfg = RPAConfig(alpha=float(alpha), allow_incomplete=allow_incomplete)
        result = engine.allocate(
            projection,
            outcome_id,
            config=cfg,
            completeness=completeness,
            provenance_fingerprint=provenance_fingerprint,
        )
        if float(alpha) != 0.0:
            result.warnings.append(
                f"Experimental alpha={alpha}; approved Phase 2.2 baseline is alpha=0."
            )
        results.append(result)
    return results
