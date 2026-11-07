"""
Fractional factorial experimental design cells (Phase 2.9).

Independent unit = one generated trace (or a matched clean/fault pair).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Optional

from agenttrust.benchmark.dataset.seeds import DatasetSplit, SeedAllocator
from agenttrust.benchmark.faults import FaultType
from agenttrust.benchmark.manifest import (
    GENERATOR_VERSION,
    BenchmarkConfig,
    ScenarioId,
    ScaleTier,
    TopologyId,
)

DESIGN_VERSION = "experimental-design-2.9.0"
DATASET_ID = "agenttrust-experimental-2.9"

TOPOLOGIES: tuple[TopologyId, ...] = tuple(TopologyId)
SCENARIOS: tuple[ScenarioId, ...] = tuple(ScenarioId)
FAULTS: tuple[FaultType, ...] = tuple(FaultType)
FAULT_SCALES: tuple[ScaleTier, ...] = (ScaleTier.S1, ScaleTier.S2)


@dataclass(frozen=True)
class TraceSpec:
    """One trace to generate."""

    split: str
    role: str  # clean_core | pair_clean | pair_fault
    scenario_id: ScenarioId
    topology_id: TopologyId
    scale_tier: ScaleTier
    seed: int
    base_seed: int
    replicate: int
    fault_types: tuple[str, ...]
    incomplete: bool
    matched_pair_id: Optional[str]
    cell_index: int

    def to_config(self) -> BenchmarkConfig:
        return BenchmarkConfig(
            scenario_id=self.scenario_id,
            topology_id=self.topology_id,
            scale_tier=self.scale_tier,
            seed=self.seed,
            fault_types=self.fault_types,
            incomplete=self.incomplete,
            generator_version=GENERATOR_VERSION,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scenario_id"] = self.scenario_id.value
        d["topology_id"] = self.topology_id.value
        d["scale_tier"] = self.scale_tier.value
        return d


def _scenario_rotated(cell_index: int) -> ScenarioId:
    return SCENARIOS[cell_index % len(SCENARIOS)]


def split_replicates(split: DatasetSplit) -> dict[str, int]:
    """Replicate counts per block for each split."""
    if split == DatasetSplit.DEVELOPMENT:
        return {"clean": 2, "fault": 2, "fault_scales": 1}  # S1 only
    if split == DatasetSplit.VALIDATION:
        return {"clean": 3, "fault": 2, "fault_scales": 2}  # S1+S2
    if split == DatasetSplit.HELDOUT_TEST:
        return {"clean": 5, "fault": 3, "fault_scales": 2}
    raise ValueError(split)


def iter_trace_specs(split: DatasetSplit) -> Iterator[TraceSpec]:
    reps = split_replicates(split)
    alloc = SeedAllocator(split)
    cell = 0

    # --- Clean core: topology × scale × R, scenario rotated ---
    for topo in TOPOLOGIES:
        for scale in ScaleTier:
            for r in range(reps["clean"]):
                scenario = _scenario_rotated(cell)
                seed = alloc.next_seed()
                yield TraceSpec(
                    split=split.value,
                    role="clean_core",
                    scenario_id=scenario,
                    topology_id=topo,
                    scale_tier=scale,
                    seed=seed,
                    base_seed=seed,
                    replicate=r,
                    fault_types=(),
                    incomplete=False,
                    matched_pair_id=None,
                    cell_index=cell,
                )
                cell += 1

    # --- Fault block with matched cleans ---
    n_fault_scales = reps["fault_scales"]
    scales = FAULT_SCALES[:n_fault_scales]
    for fault in FAULTS:
        for topo in TOPOLOGIES:
            for scale in scales:
                for r in range(reps["fault"]):
                    scenario = _scenario_rotated(cell)
                    pair_id = (
                        f"{split.value}|{topo.value}|{scale.value}|"
                        f"{scenario.value}|{fault.value}|r{r}|c{cell}"
                    )
                    incomplete = fault == FaultType.INCOMPLETE_TRACE
                    clean_seed = alloc.next_seed()
                    fault_seed = alloc.next_seed()
                    yield TraceSpec(
                        split=split.value,
                        role="pair_clean",
                        scenario_id=scenario,
                        topology_id=topo,
                        scale_tier=scale,
                        seed=clean_seed,
                        base_seed=clean_seed,
                        replicate=r,
                        fault_types=(),
                        incomplete=False,
                        matched_pair_id=pair_id,
                        cell_index=cell,
                    )
                    yield TraceSpec(
                        split=split.value,
                        role="pair_fault",
                        scenario_id=scenario,
                        topology_id=topo,
                        scale_tier=scale,
                        seed=fault_seed,
                        base_seed=clean_seed,
                        replicate=r,
                        fault_types=(fault.value,),
                        incomplete=incomplete,
                        matched_pair_id=pair_id,
                        cell_index=cell,
                    )
                    cell += 1


def count_specs(split: DatasetSplit) -> dict[str, int]:
    specs = list(iter_trace_specs(split))
    seeds = [s.seed for s in specs]
    return {
        "n_traces": len(specs),
        "n_clean_core": sum(1 for s in specs if s.role == "clean_core"),
        "n_pair_clean": sum(1 for s in specs if s.role == "pair_clean"),
        "n_pair_fault": sum(1 for s in specs if s.role == "pair_fault"),
        "n_matched_pairs": sum(1 for s in specs if s.role == "pair_fault"),
        "n_unique_seeds": len(set(seeds)),
        "seed_min": min(seeds) if seeds else None,
        "seed_max": max(seeds) if seeds else None,
    }


def design_fingerprint() -> str:
    payload = {
        "design_version": DESIGN_VERSION,
        "dataset_id": DATASET_ID,
        "generator_version": GENERATOR_VERSION,
        "splits": {s.value: count_specs(s) for s in DatasetSplit},
        "topologies": [t.value for t in TOPOLOGIES],
        "scenarios": [s.value for s in SCENARIOS],
        "faults": [f.value for f in FAULTS],
        "fault_scales": [s.value for s in FAULT_SCALES],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def design_document_dict() -> dict[str, Any]:
    return {
        "design_version": DESIGN_VERSION,
        "dataset_id": DATASET_ID,
        "generator_version": GENERATOR_VERSION,
        "design_fingerprint_sha256": design_fingerprint(),
        "splits": {s.value: count_specs(s) for s in DatasetSplit},
        "coverage_notes": [
            "Clean core: full topology×scale; scenarios rotated (not full cross).",
            "Fault block: all 9 faults × 6 topologies × S1[/S2] × R with matched cleans.",
            "S3–S5 fault injection omitted from primary matrix (documented gap).",
            "Historical pilot seeds 1–200 excluded from experimental bands.",
        ],
    }
