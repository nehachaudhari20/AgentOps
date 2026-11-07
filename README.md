# AgentOps / AgentTrust

Research implementation of **AgentTrust**: observable provenance tracking and structural responsibility allocation for multi-agent AI workflows.

Target venue context: ACM TRUST (research prototype).

## Research objective

Provide a reproducible stack that:

1. Validates and represents multi-agent **execution events** and **artifacts**
2. Builds a typed Multi-Layer Provenance Graph (MLPG)
3. Allocates **structural** responsibility on event projections (conserved RPA)
4. Aggregates RPA allocations into an exclusive **MFAV** factor profile
5. Generates controlled **synthetic multi-agent benchmarks** with separate ground truth
6. Computes an evidence-bounded **Assurance Profile** over observable records
7. Verifies **PLHC** integrity snapshots and runs a documented **end-to-end pipeline**

## Explicit non-claims

AgentTrust **does not**:

- Reconstruct hidden LLM reasoning or internal cognition
- Prove causal influence from provenance edges alone
- Establish legal or organizational liability
- Claim W3C PROV compliance (design is PROV-inspired only)
- Treat `OBSERVED_AFTER` as causal dependence
- Treat MFAV as fault probability, trust scoring, or legal accountability
- Treat Assurance Profile scores as agent trustworthiness
- Treat synthetic pilot benchmarks as production-scale validation

## Current implementation status

| Component | Status |
|-----------|--------|
| Event/artifact schema + validation | **Phase 2.1 — active** (`agenttrust/`) |
| Typed MLPG + P1/P2 projections | **Phase 2.1 — active** |
| Conserved RPA (α=0 baseline) | **Phase 2.2 — active** (`agenttrust/attribution/`) |
| MFAV (exclusive factor aggregation) | **Phase 2.3 — active** (`agenttrust/accountability/`) |
| Synthetic benchmark generator + pilot | **Phase 2.4 — active** (`agenttrust/benchmark/`) |
| Benchmark GT integrity + fault semantics | **Phase 2.5 / 2.5.1 — active** |
| Evidence-bounded Assurance Profile | **Phase 2.7.1 — active** (`agenttrust/assurance/`) |
| PLHC (Merkle + linked checkpoints) | **Phase 2.7.1 — active** (`agenttrust/integrity/`) |
| End-to-end evaluation pipeline | **Phase 2.8 — active** (`agenttrust/pipeline/`) |
| Experimental dataset (dev/val/test) | **Phase 2.9 — active** (`agenttrust/benchmark/dataset/`) |
| Legacy prototype | Preserved under `legacy/` (historical only) |

## Active architecture

```text
Benchmark generator (optional)
        │
        ▼
events.json + artifacts.json   ← algorithm inputs only (no ground truth)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentTrustPipeline (Phase 2.8)                             │
│  validate → MLPG → P1/P2 → RPA → MFAV → PLHC → Assurance    │
└─────────────────────────────────────────────────────────────┘
```

Components remain independently usable; the pipeline orchestrates them without changing their math.

## Project tree

```text
AgentOps/
├── agenttrust/           # Active implementation
│   ├── schema/
│   ├── validation/
│   ├── mlpg/
│   ├── attribution/      # Conserved RPA (Phase 2.2)
│   ├── accountability/   # MFAV (Phase 2.3)
│   ├── benchmark/        # Synthetic corpus generator (Phase 2.4)
│   ├── assurance/        # Assurance Profile (Phase 2.6–2.7)
│   ├── integrity/        # PLHC (Phase 2.7)
│   ├── migration/
│   └── provenance_trace.py
├── legacy/               # Original prototype (not active)
├── data/
│   ├── raw/              # Immutable source inputs
│   ├── processed/        # Migrated Phase 2.1 records
│   ├── benchmarks/       # Pilot / generated corpora + separate GT
│   └── fixtures/
├── experiments/
│   ├── configs/
│   ├── scripts/
│   └── results/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── property/
│   └── fixtures/
├── docs/
│   ├── architecture/
│   ├── phase-reports/
│   ├── methodology/
│   └── research/
├── outputs/historical/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -e ".[dev]"
# or
pip install -r requirements.txt
```

Requires Python ≥ 3.10. Package discovery is configured in `pyproject.toml` (authoritative).

## Phase 2.1–2.3 usage

Provenance, conserved RPA, and MFAV:

```python
from agenttrust import ProvenanceTrace, ConservedRPA, MFAV
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)

rpa_results = ConservedRPA().allocate_from_trace(
    trace,
    projection_kind=ProjectionKind.P1_DIRECT,
)
profiles = [MFAV().compute(r, trace=trace) for r in rpa_results]
```

## Phase 2.6 usage — Assurance Profile

```python
from agenttrust import AssuranceProfileCalculator, ConservedRPA, MFAV, ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)
rpa = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)[0]
mfav = MFAV().compute(rpa, trace=trace)
assurance = AssuranceProfileCalculator().compute(
    trace, rpa_result=rpa, mfav_result=mfav
)
print(assurance.overall_status, assurance.dimensions["reference_integrity"].value)
```

The Assurance Profile reports typed evidence availability and structural consistency (algorithm `2.7.1`), including optional `audit_integrity` from PLHC (Merkle v2). It is **not** a trust score.

Architecture: [docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md](docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md)

## Phase 2.7 usage — PLHC

```python
from agenttrust import PLHC, ProvenanceTrace

trace = ProvenanceTrace()
trace.load_records(events, artifacts)
plhc = PLHC()
snap = plhc.build_snapshot(trace)
cp = plhc.create_checkpoint(snap, sequence_number=0)
result = plhc.verify_against_checkpoint(trace, cp)
print(result.status, snap.merkle_root)
```

PLHC is **tamper-evident** relative to a retained checkpoint. It is **not** immutable and does not prove causation or event occurrence.

Architecture: [docs/architecture/PHASE_2_7_PLHC.md](docs/architecture/PHASE_2_7_PLHC.md)

## Phase 2.4 usage — synthetic benchmarks

```python
from agenttrust.benchmark import (
    BenchmarkGenerator,
    BenchmarkConfig,
    ScenarioId,
    TopologyId,
    ScaleTier,
)

gen = BenchmarkGenerator()
pkg = gen.generate(
    BenchmarkConfig(
        scenario_id=ScenarioId.FINANCIAL_LOAN,
        topology_id=TopologyId.HIERARCHICAL,
        scale_tier=ScaleTier.S1,
        seed=1,
    )
)
events, artifacts = pkg.algorithm_inputs()  # no ground-truth labels
gt = pkg.ground_truth                       # separate object / files
```

Generate / validate the pilot corpus:

```bash
python experiments/scripts/generate_benchmark_pilot.py
python experiments/scripts/validate_benchmark_pilot.py --pipeline
```

Pilot outputs live under `data/benchmarks/pilot/` with **ground truth in a separate directory** from algorithm inputs. See [docs/methodology/BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md).

Scale tiers S1–S5 (5–50 agents, ~50–1000 events), six topologies, five domain scenarios, and controlled fault injection are supported. The pilot validates the generator; it is **not** a final experimental evaluation.

### Phase 2.9 experimental corpus

Design + power rationale: [docs/methodology/EXPERIMENTAL_DATASET_DESIGN.md](docs/methodology/EXPERIMENTAL_DATASET_DESIGN.md), [SAMPLE_SIZE_AND_POWER.md](docs/methodology/SAMPLE_SIZE_AND_POWER.md).

```bash
python experiments/scripts/generate_experimental_dataset.py
python experiments/scripts/validate_experimental_dataset.py
```

Output: `data/benchmarks/experimental_2_9/` with isolated `development` / `validation` / `heldout_test` splits, separate ground truth, fingerprints, and coverage reports. The independent unit is the **trace**; event totals are nested volume only.

Phase 2.5 / 2.5.1 hardens ground-truth consistency and fault semantics (incorrect tool content vs tool-call failure; conflicting outputs via structured decisions without `conflict_label`). The checked-in pilot remains Phase 2.4 (`2.4.0`); active generation uses generator `2.5.1`.

```bash
# Mode A — historical pilot (not 2.5.1 fault-semantic certification)
python experiments/scripts/validate_benchmark_pilot.py --pipeline

# Mode B — fresh strict fault matrix
python experiments/scripts/validate_phase25_fault_matrix.py
```

See [BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md) and [FINAL_EXPERIMENTAL_DATASET_PLAN.md](docs/methodology/FINAL_EXPERIMENTAL_DATASET_PLAN.md).

## Phase 2.8 — end-to-end evaluation

```python
from agenttrust import AgentTrustPipeline, PipelineConfig

pipe = AgentTrustPipeline(PipelineConfig())
result = pipe.run_trace_dir("data/benchmarks/pilot/traces/<trace_id>")
print(result.ok, result.plhc["status"], result.assurance["status"])
```

```bash
# One trace
python experiments/scripts/evaluate_agenttrust.py \
  --trace data/benchmarks/pilot/traces/<trace_id> \
  --out data/results/pipeline_2_8 --validate-only

# Pilot corpus
python experiments/scripts/evaluate_agenttrust.py \
  --corpus data/benchmarks/pilot/traces --corpus-label pilot \
  --out data/results/pipeline_2_8_pilot --validate-only
```

Pipeline docs: [docs/architecture/PHASE_2_8_PIPELINE.md](docs/architecture/PHASE_2_8_PIPELINE.md).
Ground truth under `ground_truth/` is **never** opened by the pipeline.

## Tests

```bash
python -c "from agenttrust import ProvenanceTrace, ConservedRPA, MFAV, AgentTrustPipeline"
python -c "from agenttrust.benchmark import BenchmarkGenerator"
python -m pytest tests -q
```

## Documentation

- MLPG: [docs/architecture/PHASE_2_1_MLPG.md](docs/architecture/PHASE_2_1_MLPG.md)
- RPA: [docs/architecture/PHASE_2_2_RPA.md](docs/architecture/PHASE_2_2_RPA.md)
- MFAV: [docs/architecture/PHASE_2_3_MFAV.md](docs/architecture/PHASE_2_3_MFAV.md)
- Assurance: [docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md](docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md)
- PLHC: [docs/architecture/PHASE_2_7_PLHC.md](docs/architecture/PHASE_2_7_PLHC.md)
- Pipeline: [docs/architecture/PHASE_2_8_PIPELINE.md](docs/architecture/PHASE_2_8_PIPELINE.md)
- Benchmark methodology: [docs/methodology/BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md)
- Phase reports: [docs/phase-reports/](docs/phase-reports/)

## Legacy prototype

Historical code lives in [`legacy/`](legacy/README.md). Legacy simulation generators are **not** the active Phase 2.4 path.
