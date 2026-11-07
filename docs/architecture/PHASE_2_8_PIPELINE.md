# Phase 2.8 — End-to-End AgentTrust Pipeline

## Purpose

A single deterministic orchestration path that runs MLPG → P1/P2 → RPA → MFAV → PLHC → Assurance on observable event/artifact records and emits versioned machine-readable results.

No new attribution mathematics. No trust score. Ground truth is never an algorithm input.

## Entry points

| API | Role |
|-----|------|
| `agenttrust.pipeline.AgentTrustPipeline` | Library orchestration |
| `agenttrust.pipeline.PipelineConfig` | Public run configuration |
| `experiments/scripts/evaluate_agenttrust.py` | CLI for one trace or a corpus |

## Logical flow

1. Load `events.json` + `artifacts.json` (refuse ground-truth paths).
2. `ProvenanceTrace.load_records` — schema, IDs, typed refs, timestamps, cycles.
3. Build typed MLPG (via existing builder).
4. Project `P1_DIRECT` and/or `P2_ARTIFACT_BRIDGE`.
5. Identify outcome candidates; run `ConservedRPA.allocate` per eligible projection.
6. Independently validate each RPA result (`_validate_rpa_conservation_evidence`).
7. Aggregate with `MFAV.compute`; independently validate each MFAV result.
8. `PLHC.build_snapshot` → genesis checkpoint → `verify_against_checkpoint` (+ optional inclusion proof).
9. `AssuranceProfileCalculator.compute` using only validated evidence (contradicted RPA/MFAV withheld).
10. Emit `TracePipelineResult` / `CorpusPipelineSummary` (`agenttrust-pipeline-result-v1`).

## P1 vs P2

- P1: explicit `DEPENDS_ON` only.
- P2: P1 plus verified artifact bridges; edges already present as `DEPENDS_ON` are not double-counted.
- Both run on the same outcomes when configured and eligible.
- Projection eligibility and incompleteness are reported explicitly; P1 is never silently substituted for P2.

## Assurance

Dimensions unchanged from Phase 2.6.1+: `trace_completeness`, `reference_integrity`, `attribution_computability`, `attribution_sensitivity`, `factor_profile`, `audit_integrity`.

Statuses: `verified` | `incomplete` | `contradicted` | `unavailable` | `not_applicable`. No overall numeric assurance score.

## Outputs

- Per-trace JSON: validation, graph summary, projection eligibility, RPA, MFAV, PLHC, assurance, warnings/errors, versions, fingerprints.
- `timing_ms` is recorded separately and **excluded** from `deterministic_payload()`.
- Corpus summary: examined / eligible / ineligible / success / failed / hard_error counts. Failures are not concealed behind a corpus-level success.

## Configuration (`PipelineConfig`)

| Field | Default | Meaning |
|-------|---------|---------|
| `run_p1` | true | Execute P1 projection + RPA |
| `run_p2` | true | Execute P2 projection + RPA |
| `allow_incomplete_rpa` | false | Forward `RPAConfig.allow_incomplete` |
| `primary_outcome_only` | false | Attribute only first outcome candidate |
| `include_inclusion_proof` | true | Prove inclusion of one leaf |

## CLI

```bash
# One trace
python experiments/scripts/evaluate_agenttrust.py --trace data/benchmarks/pilot/traces/<id> --out data/results/pipeline_2_8 --validate-only

# Pilot corpus
python experiments/scripts/evaluate_agenttrust.py --corpus data/benchmarks/pilot/traces --corpus-label pilot --out data/results/pipeline_2_8_pilot --validate-only

# P1 only, allow incomplete
python experiments/scripts/evaluate_agenttrust.py --corpus ... --no-p2 --allow-incomplete
```

Exit code is non-zero if any trace fails or hard-errors (fail-closed).

Output field reference: [PHASE_2_8_OUTPUT_SCHEMA.md](PHASE_2_8_OUTPUT_SCHEMA.md).

## Related specialized validators

Existing scripts remain for focused checks; the pipeline is the primary E2E runner:

- `validate_benchmark_pilot.py`
- `validate_phase25_fault_matrix.py`
- `validate_plhc.py`
- `evaluate_assurance_profiles.py`
