"""
Synthetic multi-agent benchmark generation (Phase 2.4).

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
from agenttrust.benchmark.validation import BenchmarkValidationResult, validate_generated_trace

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
]
