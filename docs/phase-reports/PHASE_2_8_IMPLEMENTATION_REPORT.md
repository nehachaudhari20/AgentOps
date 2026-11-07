# PHASE 2.8 IMPLEMENTATION REPORT

End-to-end AgentTrust framework integration.

## 1. Starting branch and HEAD

| Item | Value |
|------|--------|
| Branch | `master` (no branch created or switched) |
| Start / expected HEAD | `0eb1e7716a56308379a71d583d1d6b9c353c985a` — PLHC crypto hardening (Phase 2.7.1) |
| Working tree at start | Clean (Phase 2.7.1 present) |
| Commit/push this phase | **Not performed** |
| End HEAD (unchanged) | `0eb1e7716a56308379a71d583d1d6b9c353c985a` |

## 2. What was integrated

Single orchestration path:

`load events/artifacts → validate → MLPG → P1/P2 → ConservedRPA → MFAV → PLHC snapshot/checkpoint/verify → Assurance Profile → machine-readable result`

Corpus runner + CLI for pilot-scale evaluation. Ground-truth directories are never opened on the algorithm path.

## 3. Existing APIs reused

| Stage | API |
|-------|-----|
| Load/validate/graph | `ProvenanceTrace.load_records`, `completeness()`, `fingerprint()`, `project()`, `outcome_candidates()` |
| RPA | `ConservedRPA.allocate`, `RPAConfig` |
| MFAV | `MFAV.compute` |
| Independent evidence checks | `_validate_rpa_conservation_evidence`, `_validate_mfav_factor_profile` (Assurance dimensions) |
| PLHC | `PLHC.build_snapshot`, `create_checkpoint`, `verify_against_checkpoint`, `prove_inclusion` / `verify_inclusion` |
| Assurance | `AssuranceProfileCalculator.compute` |

No replacement attribution mathematics. No trust score.

## 4. Changes made

### New package `agenttrust/pipeline/`
- `models.py` — `PipelineConfig`, `TracePipelineResult`, `CorpusPipelineSummary`, format `agenttrust-pipeline-result-v1`
- `io.py` — loads only `events.json` / `artifacts.json`; refuses ground-truth-like paths
- `validation.py` — wraps independent RPA/MFAV evidence validators
- `runner.py` — `AgentTrustPipeline` orchestration
- `__init__.py` — public exports

### CLI
- `experiments/scripts/evaluate_agenttrust.py` — `--trace` / `--corpus`, projection flags, `--validate-only`

### Tests
- `tests/unit/test_pipeline_28.py` — adversarial + GT leakage + determinism
- `tests/integration/test_pipeline_e2e.py` — pilot samples

### Docs
- `docs/architecture/PHASE_2_8_INTEGRATION_DESIGN.md`
- `docs/architecture/PHASE_2_8_PIPELINE.md`
- `docs/architecture/PHASE_2_8_OUTPUT_SCHEMA.md`
- README status + usage
- This report

### Package metadata
- `agenttrust.__version__` / `pyproject.toml` → `2.8.0`
- Assurance algorithm version remains `2.7.1` (no dimension semantics change)

## 5. Architectural decisions

1. **One runner** — library + thin CLI; specialized validators (`validate_*`, `evaluate_assurance_profiles`) retained.
2. **Fail-closed components** — contradicted RPA/MFAV withheld from Assurance; PLHC verification must be `verified` for pipeline `ok`.
3. **Incomplete ≠ hard failure** — without `allow_incomplete`, RPA is `ineligible` (explicit); PLHC/Assurance still run; corpus counts ineligible separately.
4. **P1/P2 independence** — both run when configured; results labeled by projection; no silent substitution.
5. **Timing excluded** from `deterministic_payload()`.
6. **Fixed checkpoint `created_at`** (`2020-01-01T00:00:00+00:00`) for reproducible genesis checkpoints in the pipeline path.

## 6. Validation and failure semantics

| Condition | Behavior |
|-----------|----------|
| Invalid / missing IO | `hard_error`, `ok=False` |
| Incomplete (default) | RPA/MFAV `ineligible`; PLHC+Assurance continue |
| Cycle | RPA `ineligible` |
| RPA/MFAV conservation contradicted | component `failed`; withheld from Assurance; `ok=False` |
| PLHC contradicted / exception | `plhc.failed`; `ok=False` |
| Corpus | exit 1 if `n_failed` or `n_hard_errors` > 0 |

## 7. Tests and actual results

```text
python -m pytest tests -q
# collected 450; all passed; exit 0
# (424 prior + 26 Phase 2.8 tests)
```

## 8. Verification scripts (actual)

```text
python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0 gt_error_total=0 incomplete=2 pipeline_eligible=66; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0 fault_types=9 leakage_violations=0; exit 0

python experiments/scripts/validate_plhc.py
# pilot n_examined=68 n_verified=68 n_errors=0
# fault_matrix n_examined=10 n_verified=10 n_errors=0; exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# pilot n_examined=68 n_profiles_ok=68 n_errors=0; exit 0
```

## 9. Pilot end-to-end pipeline (actual)

```text
python experiments/scripts/evaluate_agenttrust.py \
  --corpus data/benchmarks/pilot/traces --corpus-label pilot \
  --out data/results/pipeline_2_8_pilot --validate-only --primary-outcome-only
```

| Metric | Count |
|--------|------:|
| Examined | 68 |
| Eligible (full attribution path) | 66 |
| Ineligible (incomplete → RPA refused) | 2 |
| Successful (`ok=True`) | 68 |
| Failed | 0 |
| Hard errors | 0 |

Ineligible IDs (RPA skipped; PLHC+Assurance still verified):

- `bench-financial_loan-sequential-S1-s100-missing_dependency-cmp`
- `bench-fraud_investigation-sequential-S1-s106-incomplete_trace-inc`

CLI exit 0. Output validation: ok.

## 10. Known limitations

- Pipeline creates a **local genesis checkpoint** for round-trip verify; it does not claim external anchoring or immutability.
- `primary_outcome_only` used for pilot corpus timing; full multi-outcome runs are supported and tested.
- Historical pilot remains generator `2.4.0`; Phase 2.5.1 fault semantics certified via separate fault-matrix script.
- `provenance_coverage` remains consolidated into `reference_integrity` (not reintroduced).
- Results under `data/results/pipeline_2_8_pilot/` are generated artifacts (not committed in this phase).

## 11. Exact execution commands

```bash
python -m pytest tests -q
python experiments/scripts/validate_benchmark_pilot.py --pipeline
python experiments/scripts/validate_phase25_fault_matrix.py
python experiments/scripts/validate_plhc.py
python experiments/scripts/evaluate_assurance_profiles.py
python experiments/scripts/evaluate_agenttrust.py --corpus data/benchmarks/pilot/traces --corpus-label pilot --out data/results/pipeline_2_8_pilot --validate-only --primary-outcome-only
```

## 12. Incomplete work

None for Phase 2.8 scope. Phase 2.9 not started. No commit/push performed.
