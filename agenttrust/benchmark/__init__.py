"""
Synthetic multi-agent benchmark generation (Phase 2.4+) with Phase 2.5 integrity hardening.

Produces schema-valid traces and separate ground-truth packages.
Does not evaluate AgentTrust performance or claim causal attribution.
"""

from agenttrust.benchmark.faults import FaultType, InterventionRecord
from agenttrust.benchmark.generator import BenchmarkGenerator, GeneratedTrace, pilot_configs
from agenttrust.benchmark.ground_truth import BenchmarkGroundTruth
from agenttrust.benchmark.manifest import (
    GENERATOR_VERSION,
    SCALE_SPECS,
    BenchmarkConfig,
    ScenarioId,
    ScaleTier,
    TopologyId,
    TraceManifest,
)
from agenttrust.benchmark.validation import (
    BenchmarkValidationResult,
    load_and_validate_trace_dir,
    validate_generated_trace,
    validate_package,
)
from agenttrust.benchmark.dataset import (
    DATASET_ID,
    DESIGN_VERSION,
    DatasetSplit,
    design_fingerprint,
)

__all__ = [
    "GENERATOR_VERSION",
    "SCALE_SPECS",
    "ScaleTier",
    "TopologyId",
    "ScenarioId",
    "BenchmarkConfig",
    "TraceManifest",
    "BenchmarkGenerator",
    "GeneratedTrace",
    "pilot_configs",
    "FaultType",
    "InterventionRecord",
    "BenchmarkGroundTruth",
    "BenchmarkValidationResult",
    "validate_generated_trace",
    "validate_package",
    "load_and_validate_trace_dir",
    "DATASET_ID",
    "DESIGN_VERSION",
    "DatasetSplit",
    "design_fingerprint",
]
