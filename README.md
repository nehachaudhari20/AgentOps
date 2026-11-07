# AgentTrust

Research prototype for **observable provenance**, **structural responsibility allocation**, and **evidence-bounded integrity checks** in multi-agent AI workflows.

Target context: ACM TRUST–style research. Synthetic benchmarks only unless otherwise stated.

## What it does

1. Validates event and artifact records and builds a typed **Multi-Layer Provenance Graph (MLPG)** with P1 (direct dependency) and P2 (artifact-aware) projections.
2. Runs **Conserved RPA** (backward responsibility flow) and aggregates allocations with **MFAV**.
3. Builds an evidence-bounded **Assurance Profile** (dimension statuses, not a trust score).
4. Constructs **PLHC** Merkle snapshots and checkpoint verification (tamper-evident relative to a retained checkpoint).
5. Ships a synthetic **benchmark generator**, isolated **dev/validation/held-out** corpora, **baselines**, and **evaluation metrics**.

## What it does not claim

- Hidden LLM reasoning reconstruction  
- Causal or legal liability  
- W3C PROV or Certificate-Transparency compliance  
- Immutable / externally anchored storage  
- Universal agent trustworthiness or production validation  
- That synthetic reference allocations are real-world ground truth  

## Install

Requires **Python ≥ 3.10**.

```bash
pip install -e ".[dev]"
# or
pip install -r requirements.txt
pip install -e .
```

Tested freeze environment: see [docs/methodology/ENVIRONMENT.md](docs/methodology/ENVIRONMENT.md).

## Quick start

```python
from agenttrust import ProvenanceTrace, ConservedRPA, MFAV, PLHC, AgentTrustPipeline
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)

rpa = ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)[0]
mfav = MFAV().compute(rpa, trace=trace)

plhc = PLHC()
snap = plhc.build_snapshot(trace)
cp = plhc.create_checkpoint(snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00")
print(plhc.verify_against_checkpoint(trace, cp).status)

# End-to-end orchestration (algorithm inputs only — never reads ground truth)
result = AgentTrustPipeline().run_trace_dir("data/benchmarks/pilot/traces/<trace_id>")
print(result.ok, result.plhc["status"], result.assurance["status"])
```

## Repository layout

```text
agenttrust/          # Library: schema, MLPG, RPA, MFAV, benchmark, assurance, integrity, pipeline, evaluation
data/benchmarks/     # Pilot + experimental corpora (GT separated from events/artifacts)
experiments/scripts/ # Generators, validators, pipeline, baselines, reproducibility
tests/               # Unit, integration, property tests
docs/                # Architecture, methodology, results, phase reports (historical)
legacy/              # Retired prototype (not the active path)
```

## Benchmarks and evaluation

- **Pilot corpus** (`data/benchmarks/pilot/`): historical generator regression.  
- **Experimental corpus** (`data/benchmarks/experimental_2_9/`): development / validation / held-out splits; trace is the independent unit.  
- Ground truth is stored separately and must not be fed as algorithm input.

```bash
python experiments/scripts/validate_benchmark_pilot.py --pipeline
python experiments/scripts/validate_experimental_dataset.py
python experiments/scripts/evaluate_agenttrust.py --corpus data/benchmarks/pilot/traces --out data/results/pipeline_smoke --validate-only
python experiments/scripts/run_baseline_comparison.py --split development --limit 5
```

## Reproducibility

```bash
python experiments/scripts/reproduce.py --all-safe
# Complete reproduction (full evaluation + Phase 2.13 validator):
python experiments/scripts/reproduce.py --complete
```

Stage-level logs and exit codes. Mandatory skipped stages cannot report complete success. Scratch under `experiments/results/repro_scratch/`; compact Phase 2.13 evidence under `experiments/results/phase_2_13/`.

Details: [docs/methodology/REPRODUCIBILITY.md](docs/methodology/REPRODUCIBILITY.md).

## Research status (Phase 2.13)

Scientific-validity corrections: paired McNemar power; attribution alignment disclosure + intervention reference; artifact-bridge corpus; stratified RQ4/RQ5; observability-aware Assurance; paired effect sizes. See [PHASE_2_13_RESEARCH_VALIDITY_REPORT.md](docs/results/PHASE_2_13_RESEARCH_VALIDITY_REPORT.md) and [PHASE_2_13_CLAIM_EVIDENCE_MATRIX.md](docs/results/PHASE_2_13_CLAIM_EVIDENCE_MATRIX.md).

## Tests

```bash
python -m pytest tests -q
```

## Documentation

| Topic | Doc |
|-------|-----|
| Environment | [ENVIRONMENT.md](docs/methodology/ENVIRONMENT.md) |
| Reproducibility | [REPRODUCIBILITY.md](docs/methodology/REPRODUCIBILITY.md) |
| Threat model / limitations | [THREAT_MODEL_AND_LIMITATIONS.md](docs/methodology/THREAT_MODEL_AND_LIMITATIONS.md) |
| Benchmark design | [BENCHMARK_DESIGN.md](docs/methodology/BENCHMARK_DESIGN.md) |
| Experimental dataset | [EXPERIMENTAL_DATASET_DESIGN.md](docs/methodology/EXPERIMENTAL_DATASET_DESIGN.md) |
| Baselines / ablations | [BASELINE_AND_ABLATION_PROTOCOL.md](docs/methodology/BASELINE_AND_ABLATION_PROTOCOL.md) |
| Statistical plan | [STATISTICAL_ANALYSIS_PLAN.md](docs/methodology/STATISTICAL_ANALYSIS_PLAN.md) |
| Evaluation results | [FINAL_EVALUATION_REPORT.md](docs/results/FINAL_EVALUATION_REPORT.md) |
| Claim–evidence matrix | [CLAIM_EVIDENCE_MATRIX.md](docs/results/CLAIM_EVIDENCE_MATRIX.md) |
| Phase 2.13 validity | [PHASE_2_13_RESEARCH_VALIDITY_REPORT.md](docs/results/PHASE_2_13_RESEARCH_VALIDITY_REPORT.md) |
| Phase 2 freeze report | [PHASE_2_FINAL_REPORT.md](docs/phase-reports/PHASE_2_FINAL_REPORT.md) |
| Architecture (MLPG / RPA / MFAV / Assurance / PLHC / Pipeline) | [docs/architecture/](docs/architecture/) |
| Paper figures (Figs. 2–6) | [docs/figures/](docs/figures/) |

## License

Proprietary / research use (see `pyproject.toml`).
