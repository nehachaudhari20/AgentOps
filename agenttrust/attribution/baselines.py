"""
Future attribution baselines (interfaces only — Phase 2.2).

Shapley-style and Markov-style allocators are reserved for later experimental
comparison. They are not implemented here and must not be reported as results.
"""

from __future__ import annotations

from typing import Any

from agenttrust.mlpg.projections import AttributionProjection


class BaselineNotImplementedError(NotImplementedError):
    pass


class ShapleyAttributionBaseline:
    """Placeholder for future Shapley-style attribution experiments."""

    name = "shapley_baseline"
    status = "not_implemented"

    def allocate(self, projection: AttributionProjection, outcome_id: str, **kwargs: Any) -> Any:
        raise BaselineNotImplementedError(
            "Shapley attribution baseline is reserved for a later experimental phase."
        )


class MarkovAttributionBaseline:
    """Placeholder for future absorbing / Markov-style allocation experiments."""

    name = "markov_baseline"
    status = "not_implemented"

    def allocate(self, projection: AttributionProjection, outcome_id: str, **kwargs: Any) -> Any:
        raise BaselineNotImplementedError(
            "Markov attribution baseline is reserved for a later experimental phase."
        )
