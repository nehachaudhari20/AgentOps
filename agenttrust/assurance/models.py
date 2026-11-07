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
ASSURANCE_ALGORITHM_VERSION = "2.6.1"

# Conservation tolerance aligned with research float policy
CONSERVATION_ABS_TOL = 1e-9
