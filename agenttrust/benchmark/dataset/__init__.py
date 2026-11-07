"""Phase 2.9 experimental dataset design, generation, and validation."""

from agenttrust.benchmark.dataset.attribution_reference import (
    ATTRIBUTION_REFERENCE_METHOD,
    GROUND_TRUTH_VERSION,
    AttributionReferenceGT,
    build_attribution_reference,
)
from agenttrust.benchmark.dataset.corpus import (
    DEFAULT_ROOT,
    GenerationResult,
    generate_split,
    write_design_and_reports,
)
from agenttrust.benchmark.dataset.design import (
    DATASET_ID,
    DESIGN_VERSION,
    TraceSpec,
    count_specs,
    design_document_dict,
    design_fingerprint,
    iter_trace_specs,
)
from agenttrust.benchmark.dataset.observability import (
    ObservabilityClass,
    observability_matrix,
    primary_class,
)
from agenttrust.benchmark.dataset.power import power_report, simulate_power
from agenttrust.benchmark.dataset.seeds import DatasetSplit, SEED_BANDS, bands_disjoint
from agenttrust.benchmark.dataset.validate_corpus import (
    aggregate_statistics,
    validate_cross_split_isolation,
    validate_split,
)

__all__ = [
    "ATTRIBUTION_REFERENCE_METHOD",
    "DATASET_ID",
    "DEFAULT_ROOT",
    "DESIGN_VERSION",
    "GROUND_TRUTH_VERSION",
    "AttributionReferenceGT",
    "DatasetSplit",
    "GenerationResult",
    "ObservabilityClass",
    "SEED_BANDS",
    "TraceSpec",
    "aggregate_statistics",
    "bands_disjoint",
    "build_attribution_reference",
    "count_specs",
    "design_document_dict",
    "design_fingerprint",
    "generate_split",
    "iter_trace_specs",
    "observability_matrix",
    "power_report",
    "primary_class",
    "simulate_power",
    "validate_cross_split_isolation",
    "validate_split",
    "write_design_and_reports",
]
