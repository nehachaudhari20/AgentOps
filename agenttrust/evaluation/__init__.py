"""Phase 2.10–2.11 evaluation: baselines, metrics, comparisons."""

from agenttrust.evaluation.baselines import (
    MARKOV_STATUS,
    allocate_b0_uniform,
    allocate_b1_last_touch,
    allocate_b2_p1_equal_share,
    allocate_b4_shapley,
    allocate_rpa,
    run_online_suite,
)
from agenttrust.evaluation.compare import evaluate_trace, run_catalog
from agenttrust.evaluation.metrics import mae, rmse, spearman, top_k_agreement
from agenttrust.evaluation.schema import AllocationResult, COMPARISON_FORMAT_VERSION

__all__ = [
    "COMPARISON_FORMAT_VERSION",
    "MARKOV_STATUS",
    "AllocationResult",
    "allocate_b0_uniform",
    "allocate_b1_last_touch",
    "allocate_b2_p1_equal_share",
    "allocate_b4_shapley",
    "allocate_rpa",
    "evaluate_trace",
    "mae",
    "rmse",
    "run_catalog",
    "run_online_suite",
    "spearman",
    "top_k_agreement",
]
