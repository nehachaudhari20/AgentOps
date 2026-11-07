"""
Assurance Profile calculator (Phase 2.7).

Does not mutate inputs. Does not read benchmark ground truth.
Does not produce a trust score.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from agenttrust.accountability.result import MFAVResult
from agenttrust.assurance.dimensions import (
    evaluate_attribution_computability,
    evaluate_attribution_sensitivity,
    evaluate_audit_integrity,
    evaluate_factor_profile,
    evaluate_reference_integrity,
    evaluate_trace_completeness,
)
from agenttrust.assurance.models import (
    ASSURANCE_ALGORITHM_NAME,
    ASSURANCE_ALGORITHM_VERSION,
)
from agenttrust.assurance.result import AssuranceProfile
from agenttrust.attribution.rpa import RPAResult
from agenttrust.integrity.result import IntegrityVerificationResult
from agenttrust.provenance_trace import ProvenanceTrace


class AssuranceProfileCalculator:
    """Deterministic evidence-bounded Assurance Profile builder."""

    def compute(
        self,
        trace: ProvenanceTrace,
        *,
        rpa_result: Optional[RPAResult] = None,
        mfav_result: Optional[MFAVResult] = None,
        mfav_p1: Optional[MFAVResult] = None,
        mfav_p2: Optional[MFAVResult] = None,
        plhc_result: Optional[IntegrityVerificationResult] = None,
    ) -> AssuranceProfile:
        """
        Compute an Assurance Profile from a loaded ProvenanceTrace and optional
        RPA/MFAV/PLHC results supplied by the caller.

        Ground-truth labels are never consulted.
        """
        before_fp = trace.fingerprint()

        dims = {
            "trace_completeness": evaluate_trace_completeness(trace),
            "reference_integrity": evaluate_reference_integrity(trace),
            "attribution_computability": evaluate_attribution_computability(rpa_result),
            "attribution_sensitivity": evaluate_attribution_sensitivity(mfav_p1, mfav_p2),
            "factor_profile": evaluate_factor_profile(mfav_result),
            "audit_integrity": evaluate_audit_integrity(plhc_result),
        }

        after_fp = trace.fingerprint()
        if before_fp != after_fp:
            raise RuntimeError("AssuranceProfileCalculator mutated provenance graph.")

        overall = AssuranceProfile.compute_overall(dims)

        profile = AssuranceProfile(
            algorithm_name=ASSURANCE_ALGORITHM_NAME,
            algorithm_version=ASSURANCE_ALGORITHM_VERSION,
            outcome_id=rpa_result.outcome_id if rpa_result else (mfav_result.outcome_id if mfav_result else None),
            projection_kind=(
                rpa_result.projection_kind
                if rpa_result
                else (mfav_result.projection_kind if mfav_result else None)
            ),
            dimensions=dims,
            overall_status=overall,
            warnings=[w for d in dims.values() for w in d.warnings],
            reproducibility={
                "algorithm": ASSURANCE_ALGORITHM_NAME,
                "version": ASSURANCE_ALGORITHM_VERSION,
                "provenance_fingerprint": before_fp,
                "has_rpa": rpa_result is not None,
                "has_mfav": mfav_result is not None,
                "has_mfav_p1": mfav_p1 is not None,
                "has_mfav_p2": mfav_p2 is not None,
                "has_plhc": plhc_result is not None,
                "dimension_ids": sorted(dims.keys()),
            },
        )
        _ = deepcopy(profile.to_dict())
        return profile
