"""
Aggregate exclusive event-level RPA allocations into MFAV factor / entity totals.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Mapping, Optional, Sequence

from agenttrust.accountability.classifier import Classification, EventFactorClassifier
from agenttrust.accountability.result import (
    EntityContribution,
    EventAssignment,
    MFAVResult,
    MFAVStatus,
)
from agenttrust.accountability.taxonomy import (
    DEFAULT_MAPPING_POLICY,
    FACTOR_ORDER,
    MFAVFactor,
    TAXONOMY_VERSION,
)
from agenttrust.attribution.rpa import RPAResult
from agenttrust.schema.event import EventRecord

ALGORITHM_NAME = "mfav_exclusive_factor_aggregation"
ALGORITHM_VERSION = "2.3.0"
CONSERVATION_TOL = 1e-12


class MFAVError(ValueError):
    """Raised when MFAV cannot aggregate under documented guards."""


def _is_bad_allocation(value: float) -> bool:
    return math.isnan(value) or math.isinf(value) or value < 0.0


class MFAVAggregator:
    """Factor- and entity-level aggregation over exclusive classifications."""

    def __init__(
        self,
        *,
        mapping_policy: str = DEFAULT_MAPPING_POLICY,
        classifier: Optional[EventFactorClassifier] = None,
    ) -> None:
        self.mapping_policy = mapping_policy
        self.classifier = classifier or EventFactorClassifier(policy=mapping_policy)

    def aggregate(
        self,
        rpa_result: RPAResult,
        events_by_id: Mapping[str, EventRecord],
        *,
        include_zero_nodes: bool = False,
    ) -> MFAVResult:
        """
        Aggregate ``rpa_result.node_allocations`` into exclusive factor totals.

        Does not mutate ``rpa_result`` or event records. Allocations for nodes
        absent from ``events_by_id`` are classified as ``other`` with a warning
        (projection-only ids), never inventing identities.
        """
        warnings: list[str] = []
        raw_factors = MFAVResult.empty_factor_map()
        secondary_totals: dict[str, float] = defaultdict(float)
        entity_acc: dict[tuple[str, str, str, bool], list[str]] = defaultdict(list)
        entity_alloc: dict[tuple[str, str, str, bool], float] = defaultdict(float)
        assignments: list[EventAssignment] = []

        incoming_total = 0.0
        # Deterministic iteration
        for event_id in sorted(rpa_result.node_allocations.keys()):
            alloc = float(rpa_result.node_allocations[event_id])
            if _is_bad_allocation(alloc):
                raise MFAVError(
                    f"Invalid RPA allocation for {event_id!r}: {alloc!r} "
                    "(negative, NaN, or infinite values are rejected)."
                )
            if alloc == 0.0 and not include_zero_nodes:
                continue
            incoming_total += alloc

            event = events_by_id.get(event_id)
            if event is None:
                classification = Classification(
                    event_id=event_id,
                    factor=MFAVFactor.OTHER,
                    entity_id=event_id,
                    entity_kind="event",
                    unidentified=False,
                    secondary_subtypes=(),
                    policy=self.mapping_policy,
                    rationale="allocation node missing from event records → other",
                    warnings=(
                        f"Event {event_id!r} present in RPA allocations but absent "
                        "from provided event records; mapped to other.",
                    ),
                )
            else:
                classification = self.classifier.classify(event)

            warnings.extend(classification.warnings)
            factor = classification.factor.value
            raw_factors[factor] = raw_factors.get(factor, 0.0) + alloc

            for tag in classification.secondary_subtypes:
                secondary_totals[tag] += alloc

            key = (
                factor,
                classification.entity_id,
                classification.entity_kind,
                classification.unidentified,
            )
            entity_alloc[key] += alloc
            entity_acc[key].append(event_id)

            assignments.append(
                EventAssignment(
                    event_id=event_id,
                    factor=factor,
                    allocation=alloc,
                    entity_id=classification.entity_id,
                    entity_kind=classification.entity_kind,
                    unidentified=classification.unidentified,
                    secondary_subtypes=classification.secondary_subtypes,
                    rationale=classification.rationale,
                )
            )

        factor_total = sum(raw_factors[f.value] for f in FACTOR_ORDER)
        conservation_error = abs(factor_total - incoming_total)

        if conservation_error > CONSERVATION_TOL:
            raise MFAVError(
                f"Factor aggregation failed conservation: factor_total={factor_total}, "
                f"incoming={incoming_total}, error={conservation_error}"
            )

        normalized: Optional[dict[str, float]]
        if factor_total > 0.0 and math.isfinite(factor_total):
            normalized = {
                f.value: raw_factors[f.value] / factor_total for f in FACTOR_ORDER
            }
        else:
            # Zero / undefined — do not epsilon-normalize or invent a uniform vector
            normalized = None

        entity_contributions: list[EntityContribution] = []
        unidentified: list[EntityContribution] = []
        for key in sorted(entity_alloc.keys(), key=lambda k: (k[0], k[1], k[2], k[3])):
            factor, entity_id, entity_kind, is_unidentified = key
            contrib = EntityContribution(
                factor=factor,
                entity_id=entity_id,
                entity_kind=entity_kind,
                allocation=entity_alloc[key],
                unidentified=is_unidentified,
                event_ids=tuple(sorted(entity_acc[key])),
            )
            entity_contributions.append(contrib)
            if is_unidentified:
                unidentified.append(contrib)

        status, complete = self._status(rpa_result, factor_total)

        return MFAVResult(
            outcome_id=rpa_result.outcome_id,
            projection_kind=rpa_result.projection_kind,
            rpa_algorithm_name=rpa_result.algorithm_name,
            rpa_algorithm_version=rpa_result.algorithm_version,
            rpa_alpha=float(rpa_result.alpha),
            parent_allocation_policy=rpa_result.parent_allocation_policy,
            mfav_algorithm_name=ALGORITHM_NAME,
            mfav_algorithm_version=ALGORITHM_VERSION,
            taxonomy_version=TAXONOMY_VERSION,
            mapping_policy=self.mapping_policy,
            raw_factor_allocations={f.value: raw_factors[f.value] for f in FACTOR_ORDER},
            normalized_factor_vector=normalized,
            total_raw_allocation=factor_total,
            conservation_error=conservation_error,
            status=status,
            complete=complete,
            entity_contributions=entity_contributions,
            event_assignments=sorted(assignments, key=lambda a: a.event_id),
            secondary_subtype_totals=dict(sorted(secondary_totals.items())),
            unidentified_contributions=unidentified,
            classification_warnings=warnings,
            rpa_warnings=list(rpa_result.warnings),
            overridden_guards=list(rpa_result.overridden_guards),
            rpa_completeness=dict(rpa_result.completeness),
            reproducibility={
                "mfav_algorithm": ALGORITHM_NAME,
                "mfav_version": ALGORITHM_VERSION,
                "taxonomy_version": TAXONOMY_VERSION,
                "mapping_policy": self.mapping_policy,
                "outcome_id": rpa_result.outcome_id,
                "projection_kind": rpa_result.projection_kind,
                "rpa_algorithm": rpa_result.algorithm_name,
                "rpa_version": rpa_result.algorithm_version,
                "rpa_alpha": float(rpa_result.alpha),
                "parent_allocation_policy": rpa_result.parent_allocation_policy,
                "rpa_reproducibility": dict(rpa_result.reproducibility),
                "n_event_assignments": len(assignments),
            },
        )

    @staticmethod
    def _status(rpa_result: RPAResult, factor_total: float) -> tuple[MFAVStatus, bool]:
        if factor_total == 0.0:
            return MFAVStatus.ZERO_ALLOCATION, False
        if rpa_result.overridden_guards:
            return MFAVStatus.OVERRIDDEN, False
        incomplete = bool(rpa_result.completeness.get("incomplete"))
        if incomplete:
            return MFAVStatus.INCOMPLETE, False
        if not math.isfinite(factor_total):
            return MFAVStatus.UNDEFINED, False
        return MFAVStatus.COMPLETE, True
