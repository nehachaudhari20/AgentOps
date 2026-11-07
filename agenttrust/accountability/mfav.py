"""
Multi-Factor Accountability Vector (MFAV) — public API.

Maps conserved RPA event allocations onto an exclusive factor taxonomy.
Does not recompute responsibility, infer causality, or produce trust scores.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping, Optional, Sequence

from agenttrust.accountability.aggregator import MFAVAggregator, MFAVError
from agenttrust.accountability.classifier import EventFactorClassifier
from agenttrust.accountability.result import MFAVResult
from agenttrust.accountability.taxonomy import DEFAULT_MAPPING_POLICY
from agenttrust.attribution.rpa import RPAResult
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.event import EventRecord


class MFAV:
    """
    Factor-level aggregation over ``RPAResult`` allocations.

    Usage::

        profiles = [MFAV().compute(r, trace=trace) for r in rpa_results]
    """

    def __init__(
        self,
        *,
        mapping_policy: str = DEFAULT_MAPPING_POLICY,
        include_zero_nodes: bool = False,
    ) -> None:
        self.mapping_policy = mapping_policy
        self.include_zero_nodes = include_zero_nodes
        self._classifier = EventFactorClassifier(policy=mapping_policy)
        self._aggregator = MFAVAggregator(
            mapping_policy=mapping_policy,
            classifier=self._classifier,
        )

    def compute(
        self,
        rpa_result: RPAResult,
        *,
        trace: Optional[ProvenanceTrace] = None,
        events: Optional[Sequence[EventRecord] | Mapping[str, EventRecord]] = None,
    ) -> MFAVResult:
        """
        Compute an MFAV profile for one RPA outcome result.

        Provide either ``trace`` or ``events``. Does not mutate inputs or rerun RPA.
        """
        events_by_id = self._resolve_events(trace=trace, events=events)
        # Snapshot allocations so caller mutations after compute cannot affect result building mid-flight
        snapshot = deepcopy(rpa_result.to_dict())
        frozen = RPAResult(
            outcome_id=snapshot["outcome_id"],
            projection_kind=snapshot["projection_kind"],
            algorithm_name=snapshot["algorithm_name"],
            algorithm_version=snapshot["algorithm_version"],
            alpha=snapshot["alpha"],
            parent_allocation_policy=snapshot["parent_allocation_policy"],
            node_allocations=dict(snapshot["node_allocations"]),
            root_allocations=dict(snapshot["root_allocations"]),
            conservation=dict(snapshot["conservation"]),
            completeness=dict(snapshot["completeness"]),
            cycle_diagnostics=dict(snapshot["cycle_diagnostics"]),
            config=dict(snapshot["config"]),
            reproducibility=dict(snapshot["reproducibility"]),
            warnings=list(snapshot["warnings"]),
            overridden_guards=list(snapshot["overridden_guards"]),
        )
        return self._aggregator.aggregate(
            frozen,
            events_by_id,
            include_zero_nodes=self.include_zero_nodes,
        )

    def compute_many(
        self,
        rpa_results: Sequence[RPAResult],
        *,
        trace: Optional[ProvenanceTrace] = None,
        events: Optional[Sequence[EventRecord] | Mapping[str, EventRecord]] = None,
    ) -> list[MFAVResult]:
        """Independent per-outcome MFAV profiles (no cross-outcome merge)."""
        return [
            self.compute(r, trace=trace, events=events) for r in rpa_results
        ]

    @staticmethod
    def _resolve_events(
        *,
        trace: Optional[ProvenanceTrace],
        events: Optional[Sequence[EventRecord] | Mapping[str, EventRecord]],
    ) -> dict[str, EventRecord]:
        if events is not None and trace is not None:
            raise MFAVError("Provide either trace or events, not both.")
        if events is None and trace is None:
            raise MFAVError("MFAV.compute requires trace=... or events=...")
        if trace is not None:
            return {e.event_id: e for e in trace.events}
        if isinstance(events, Mapping):
            return dict(events)
        return {e.event_id: e for e in events}  # type: ignore[union-attr]
