"""
Fault observability declarations (Phase 2.9).

Classifies what can be inferred from public evidence vs ground truth.
Does not claim Assurance Profile detects every injected fault.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from agenttrust.benchmark.faults import FaultType


class ObservabilityClass(str, Enum):
    DIRECTLY_OBSERVABLE = "directly_observable"
    INDIRECT_INCONSISTENCY = "indirect_inconsistency"
    REQUIRES_GROUND_TRUTH = "requires_ground_truth"
    NOT_RELIABLY_DETECTABLE = "not_reliably_detectable"


# Primary class per fault family (may list secondary notes).
FAULT_OBSERVABILITY: dict[str, dict[str, Any]] = {
    FaultType.MISSING_DEPENDENCY.value: {
        "primary": ObservabilityClass.INDIRECT_INCONSISTENCY.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": True,
        "notes": [
            "Phantom dependency IDs appear in public dependency_event_ids.",
            "Incomplete/reference_integrity dimensions can surface missing parents.",
        ],
    },
    FaultType.INCORRECT_TOOL_OUTPUT.value: {
        "primary": ObservabilityClass.REQUIRES_GROUND_TRUTH.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": False,
        "notes": [
            "Public content_hash is the planted wrong hash; expected hash lives only in GT.",
            "Without GT, the call still looks like a successful tool event.",
        ],
    },
    FaultType.TOOL_CALL_FAILURE.value: {
        "primary": ObservabilityClass.DIRECTLY_OBSERVABLE.value,
        "secondary": [],
        "assurance_may_flag": False,
        "notes": [
            "status=failure is public.",
            "Assurance Profile does not score tool reliability as a trust metric.",
        ],
    },
    FaultType.ARTIFACT_CORRUPTION.value: {
        "primary": ObservabilityClass.REQUIRES_GROUND_TRUTH.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": False,
        "notes": [
            "Observed sentinel hash is public; mismatch vs expected requires GT.",
        ],
    },
    FaultType.RETRY_STORM.value: {
        "primary": ObservabilityClass.DIRECTLY_OBSERVABLE.value,
        "secondary": [],
        "assurance_may_flag": False,
        "notes": ["Retry chain and RETRIES edges are public structural evidence."],
    },
    FaultType.DELEGATION_FAILURE.value: {
        "primary": ObservabilityClass.INDIRECT_INCONSISTENCY.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": True,
        "notes": [
            "Missing callee or failed callee can appear as broken INVOKES / status.",
        ],
    },
    FaultType.CONFLICTING_OUTPUTS.value: {
        "primary": ObservabilityClass.NOT_RELIABLY_DETECTABLE.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": False,
        "notes": [
            "Two agents may emit disagreeing structured outputs publicly.",
            "Disagreement does not identify which agent is correct without external GT.",
        ],
    },
    FaultType.INCOMPLETE_TRACE.value: {
        "primary": ObservabilityClass.INDIRECT_INCONSISTENCY.value,
        "secondary": [ObservabilityClass.REQUIRES_GROUND_TRUTH.value],
        "assurance_may_flag": True,
        "notes": [
            "Missing parents/events are observable as incompleteness.",
            "Intentional vs accidental incompleteness requires GT quality flags.",
        ],
    },
    FaultType.MISLEADING_OBSERVATION.value: {
        "primary": ObservabilityClass.NOT_RELIABLY_DETECTABLE.value,
        "secondary": [ObservabilityClass.DIRECTLY_OBSERVABLE.value],
        "assurance_may_flag": False,
        "notes": [
            "Delayed/misleading OBSERVED_AFTER-style signals are not structural DEPENDS_ON.",
            "Without GT intent, timing anomalies are ambiguous.",
        ],
    },
}


def observability_matrix() -> dict[str, Any]:
    return {
        "matrix_version": "2.9.0",
        "disclaimer": (
            "Declarations describe evidence availability, not AgentTrust detection guarantees. "
            "Assurance Profile is not assumed to detect every injected fault."
        ),
        "classes": [c.value for c in ObservabilityClass],
        "faults": dict(FAULT_OBSERVABILITY),
    }


def primary_class(fault_type: str) -> str:
    entry = FAULT_OBSERVABILITY.get(fault_type)
    if not entry:
        raise KeyError(f"Unknown fault type for observability: {fault_type}")
    return str(entry["primary"])
