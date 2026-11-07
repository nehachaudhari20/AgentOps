"""
Accountability — Multi-Factor Accountability Vector (MFAV), Phase 2.3.

Exclusive factor aggregation over conserved RPA allocations.
Not legal liability, causal attribution, or trust scoring.
"""

from agenttrust.accountability.aggregator import MFAVError
from agenttrust.accountability.classifier import Classification, EventFactorClassifier
from agenttrust.accountability.mfav import MFAV
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
    MAPPING_POLICY_CATEGORY_PRIMARY_V1,
    SecondarySubtype,
    TAXONOMY_VERSION,
    UNIDENTIFIED_ENTITY_KEY,
)

__all__ = [
    "MFAV",
    "MFAVError",
    "MFAVResult",
    "MFAVStatus",
    "MFAVFactor",
    "FACTOR_ORDER",
    "TAXONOMY_VERSION",
    "DEFAULT_MAPPING_POLICY",
    "MAPPING_POLICY_CATEGORY_PRIMARY_V1",
    "SecondarySubtype",
    "UNIDENTIFIED_ENTITY_KEY",
    "EventFactorClassifier",
    "Classification",
    "EntityContribution",
    "EventAssignment",
]
