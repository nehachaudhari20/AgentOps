# AgentOps / AgentTrust

Research implementation of **AgentTrust**: observable provenance tracking and structural responsibility allocation for multi-agent AI workflows.

Target venue context: ACM TRUST (research prototype).

## Research objective

Provide a reproducible stack that:

1. Validates and represents multi-agent **execution events** and **artifacts**
2. Builds a typed Multi-Layer Provenance Graph (MLPG)
3. Allocates **structural** responsibility on event projections (conserved RPA)
4. Aggregates RPA allocations into an exclusive **MFAV** factor profile

## Explicit non-claims

AgentTrust **does not**:

- Reconstruct hidden LLM reasoning or internal cognition
- Prove causal influence from provenance edges alone
- Establish legal or organizational liability
- Claim W3C PROV compliance (design is PROV-inspired only)
- Treat `OBSERVED_AFTER` as causal dependence
- Treat MFAV as fault probability, trust scoring, or legal accountability

## Current implementation status

| Component | Status |
|-----------|--------|
| Event/artifact schema + validation | **Phase 2.1 — active** (`agenttrust/`) |
| Typed MLPG + P1/P2 projections | **Phase 2.1 — active** |
| Conserved RPA (α=0 baseline) | **Phase 2.2 — active** (`agenttrust/attribution/`) |
| MFAV (exclusive factor aggregation) | **Phase 2.3 — active** (`agenttrust/accountability/`) |
| Assurance / CTSM redesign | Not implemented (package reserved) |
| PLHC redesign | Not implemented (package reserved) |
| Legacy prototype | Preserved under `legacy/` (historical only) |

## Active architecture

```text
Raw / processed events
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
│   ├── assurance/        # Reserved
│   ├── integrity/        # Reserved
│   ├── migration/
│   └── provenance_trace.py
├── legacy/               # Original prototype (not active)
├── data/
│   ├── raw/              # Immutable source inputs
│   ├── processed/        # Migrated Phase 2.1 records
│   ├── benchmarks/
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
├── outputs/historical/   # Legacy figures (not new results)
├── pyproject.toml        # Package / pytest source of truth
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -e ".[dev]"
# or
pip install -r requirements.txt
```

Requires Python ≥ 3.10. Package discovery is configured in `pyproject.toml` (authoritative). `requirements.txt` mirrors runtime/dev pins for simple setups.

## Phase 2.1 usage — provenance

```python
from agenttrust import ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
report = trace.load_records(events, artifacts)
_ = trace.project(ProjectionKind.P1_DIRECT)
_ = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
```

Migrate legacy JSON without modifying raw bytes:

```bash
python -m agenttrust.migration.cli
```

## Phase 2.2 usage — conserved RPA

```python
from agenttrust import ConservedRPA, ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)

results = ConservedRPA().allocate_from_trace(
    trace,
    projection_kind=ProjectionKind.P1_DIRECT,
)
for r in results:
    print(r.outcome_id, r.root_allocations, r.conservation)
```

Demo script:

```bash
python experiments/scripts/run_conserved_rpa.py
```

Baseline: **α = 0** (intermediate nodes retain no local share; roots absorb). Equal parent split is a **structural convention**, not measured causal weight.

## Phase 2.3 usage — MFAV

```python
from agenttrust import ProvenanceTrace, ConservedRPA, MFAV
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)

rpa_results = ConservedRPA().allocate_from_trace(
    trace,
    projection_kind=ProjectionKind.P1_DIRECT,
)

profiles = [MFAV().compute(result, trace=trace) for result in rpa_results]
for p in profiles:
    print(p.outcome_id, p.normalized_factor_vector, p.status)
```

MFAV maps each RPA event allocation to exactly one primary factor (`agent`, `model`, `prompt`, `data`, `tool`, `execution`, `other`). Optional `model_id` / `tool_id` / memory metadata are used only when explicitly present.

## Tests

```bash
python -c "from agenttrust import ProvenanceTrace, ConservedRPA, MFAV"
python -m pytest tests -q
```

## Documentation

- Architecture (Phase 2.1 MLPG): [docs/architecture/PHASE_2_1_MLPG.md](docs/architecture/PHASE_2_1_MLPG.md)
- Architecture (Phase 2.2 RPA): [docs/architecture/PHASE_2_2_RPA.md](docs/architecture/PHASE_2_2_RPA.md)
- Architecture (Phase 2.3 MFAV): [docs/architecture/PHASE_2_3_MFAV.md](docs/architecture/PHASE_2_3_MFAV.md)
- Phase 2.1 report: [docs/phase-reports/PHASE_2_1_IMPLEMENTATION_REPORT.md](docs/phase-reports/PHASE_2_1_IMPLEMENTATION_REPORT.md)
- Phase 2.2 report: [docs/phase-reports/PHASE_2_2_IMPLEMENTATION_REPORT.md](docs/phase-reports/PHASE_2_2_IMPLEMENTATION_REPORT.md)
- Phase 2.3 report: [docs/phase-reports/PHASE_2_3_IMPLEMENTATION_REPORT.md](docs/phase-reports/PHASE_2_3_IMPLEMENTATION_REPORT.md)

## Legacy prototype

Historical code lives in [`legacy/`](legacy/README.md). It includes the original non-conserved RPA, hardcoded trust placeholders, and thin hash-chain demo. Those are **not** validated AgentTrust capabilities.

```powershell
$env:PYTHONPATH = "$PWD\legacy"
python -m experiments.run_rpa
```
