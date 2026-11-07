"""Assurance status vocabulary and shared types."""

from __future__ import annotations

from enum import Enum
from typing import Any


class AssuranceStatus(str, Enum):
    """
    Explicit status for every Assurance Profile dimension.

    Precedence (worst → best): contradicted > incomplete > unavailable >
    not_applicable > verified.
    """

    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    CONTRADICTED = "contradicted"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


STATUS_PRECEDENCE: tuple[AssuranceStatus, ...] = (
    AssuranceStatus.CONTRADICTED,
    AssuranceStatus.INCOMPLETE,
    AssuranceStatus.UNAVAILABLE,
    AssuranceStatus.NOT_APPLICABLE,
    AssuranceStatus.VERIFIED,
)


def worst_status(statuses: list[AssuranceStatus]) -> AssuranceStatus:
    if not statuses:
        return AssuranceStatus.UNAVAILABLE
    return min(statuses, key=lambda s: STATUS_PRECEDENCE.index(s))


ASSURANCE_ALGORITHM_NAME = "evidence_bounded_assurance_profile"
ASSURANCE_ALGORITHM_VERSION = "2.7.1"

# Conservation / agreement tolerances (absolute). Do not weaken to pass tests.
CONSERVATION_ABS_TOL = 1e-9
# Floating-point allowance for non-negativity of allocations
ALLOCATION_NONNEG_TOL = 1e-12
# Reported vs independently recomputed agreement
REPORT_AGREEMENT_TOL = 1e-9
