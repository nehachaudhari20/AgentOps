"""
Exclusive MFAV factor taxonomy and versioned mapping policies.

Primary factors are mutually exclusive. Secondary subtype tags (e.g. memory)
never enter primary factor totals.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

TAXONOMY_VERSION: Final[str] = "2.3.0"
MAPPING_POLICY_CATEGORY_PRIMARY_V1: Final[str] = "category_primary_v1"
DEFAULT_MAPPING_POLICY: Final[str] = MAPPING_POLICY_CATEGORY_PRIMARY_V1


class MFAVFactor(str, Enum):
    """Exclusive primary accountability factors."""

    AGENT = "agent"
    MODEL = "model"
    PROMPT = "prompt"
    DATA = "data"
    TOOL = "tool"
    EXECUTION = "execution"
    OTHER = "other"


# Stable ordered factor list for deterministic vectors / serialization
FACTOR_ORDER: tuple[MFAVFactor, ...] = (
    MFAVFactor.AGENT,
    MFAVFactor.MODEL,
    MFAVFactor.PROMPT,
    MFAVFactor.DATA,
    MFAVFactor.TOOL,
    MFAVFactor.EXECUTION,
    MFAVFactor.OTHER,
)

FACTOR_IDS: frozenset[str] = frozenset(f.value for f in MFAVFactor)


class SecondarySubtype(str, Enum):
    """
    Optional secondary tags retained beside a primary factor.

    MEMORY is a subtype of DATA only — never a primary factor.
    """

    MEMORY = "memory"


UNIDENTIFIED_ENTITY_KEY: Final[str] = "__unidentified__"
