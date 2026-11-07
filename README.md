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
| Evidence-bounded Assurance Profile | **Phase 2.6 — active** (`agenttrust/assurance/`) |
| PLHC redesign | Not implemented (package reserved) |
| Legacy prototype | Preserved under `legacy/` (historical only) |

## Active architecture

```text
Benchmark generator (optional)
        │
        ▼
Raw / processed / pilot events
        │
        ▼
┌───────────────────┐
│  ProvenanceTrace  │  schema + validation + MLPG
└─────────┬─────────┘
          │
          ├─ P1 / P2 event projections
          │
          ▼
┌───────────────────┐
│  Conserved RPA    │  structural allocation (α=0 baseline)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  MFAV             │  exclusive factor + entity aggregation
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Assurance Profile│  evidence-bounded dimension statuses
└───────────────────┘
```

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
│   ├── assurance/        # Assurance Profile (Phase 2.6)
│   ├── integrity/        # Reserved
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
print(assurance.overall_status, assurance.dimensions["provenance_coverage"].value)
```

The Assurance Profile reports evidence availability and structural consistency. It is **not** a trust score.

Architecture: [docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md](docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md)

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

Phase 2.5 / 2.5.1 hardens ground-truth consistency and fault semantics (incorrect tool content vs tool-call failure; conflicting outputs via structured decisions without `conflict_label`). The checked-in pilot remains Phase 2.4 (`2.4.0`); active generation uses generator `2.5.1`.

```bash
# Mode A — historical pilot (not 2.5.1 fault-semantic certification)
python experiments/scripts/validate_benchmark_pilot.py --pipeline

# Mode B — fresh strict fault matrix
python experiments/scripts/validate_phase25_fault_matrix.py
```

See [BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md) and [FINAL_EXPERIMENTAL_DATASET_PLAN.md](docs/methodology/FINAL_EXPERIMENTAL_DATASET_PLAN.md).

## Tests

```bash
python -c "from agenttrust import ProvenanceTrace, ConservedRPA, MFAV"
python -c "from agenttrust.benchmark import BenchmarkGenerator"
python -m pytest tests -q
```

## Documentation

- MLPG: [docs/architecture/PHASE_2_1_MLPG.md](docs/architecture/PHASE_2_1_MLPG.md)
- RPA: [docs/architecture/PHASE_2_2_RPA.md](docs/architecture/PHASE_2_2_RPA.md)
- MFAV: [docs/architecture/PHASE_2_3_MFAV.md](docs/architecture/PHASE_2_3_MFAV.md)
- Benchmark methodology: [docs/methodology/BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md)
- Phase reports: [docs/phase-reports/](docs/phase-reports/)

## Legacy prototype

Historical code lives in [`legacy/`](legacy/README.md). Legacy simulation generators are **not** the active Phase 2.4 path.
