"""
Independent validation of RPA / MFAV results for the pipeline.

Reuses Assurance Profile evidence validators — does not invent new conservation math.
"""

from __future__ import annotations

from typing import Any

from agenttrust.accountability.result import MFAVResult
from agenttrust.assurance.dimensions import (
    _validate_mfav_factor_profile,
    _validate_rpa_conservation_evidence,
)
from agenttrust.attribution.rpa import RPAResult


def validate_rpa_result(rpa: RPAResult) -> dict[str, Any]:
    """
    Independently validate an RPA result.

    Returns a machine-readable verdict using the same fail-closed rules as
    attribution_computability evidence checks.
    """
    kind, reason = _validate_rpa_conservation_evidence(rpa)
    incomplete_or_overridden = bool(rpa.overridden_guards) or bool(
        (rpa.completeness or {}).get("incomplete")
    )
    if kind is None:
        if incomplete_or_overridden:
            return {
                "valid": True,
                "status": "incomplete",
                "reason": "conservation valid but incomplete/overridden guards present",
            }
        return {"valid": True, "status": "verified", "reason": "conservation evidence valid"}
    if kind == "unavailable":
        return {"valid": False, "status": "unavailable", "reason": reason}
    return {"valid": False, "status": "contradicted", "reason": reason}


def validate_mfav_result(mfav: MFAVResult) -> dict[str, Any]:
    """Independently validate an MFAV result (factor_profile evidence rules)."""
    kind, reason = _validate_mfav_factor_profile(mfav)
    if kind is None:
        return {"valid": True, "status": "verified", "reason": "factor profile evidence valid"}
    if kind == "unavailable":
        return {"valid": False, "status": "unavailable", "reason": reason}
    if kind == "incomplete":
        return {"valid": True, "status": "incomplete", "reason": reason}
    return {"valid": False, "status": "contradicted", "reason": reason}


def rpa_usable_for_assurance(validation: dict[str, Any]) -> bool:
    """Only feed RPA into Assurance when evidence is verified or incomplete (not contradicted)."""
    return validation.get("status") in ("verified", "incomplete") and validation.get("valid") is not False


def mfav_usable_for_assurance(validation: dict[str, Any]) -> bool:
    return validation.get("status") in ("verified", "incomplete")
