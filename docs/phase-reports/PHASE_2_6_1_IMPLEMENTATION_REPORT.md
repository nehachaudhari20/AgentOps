# PHASE 2.6.1 IMPLEMENTATION REPORT

Assurance Profile correctness and evaluation hardening.

## 1. Starting commit and branch

| Item | Value |
|------|--------|
| Branch | `master` |
| Start commit | `7c073da0d37d5bb3272965916acf6ed58b69d386` — Add assurance dimensions over provenance, RPA, and MFAV… |
| Working tree at start | Clean |
| Implementation commit | `270127ea0ed57dd1639b86a5e75e599551acd6a1` — Evluation hardening |

**Historical note (corrected in Phase 2.6.2):** The original draft of this report stated that commit/push was not performed. The Phase 2.6.1 implementation was subsequently committed on `master` as `270127e`. That commit is the authoritative record of the 2.6.1 tree; this note does not rewrite earlier working-session instructions, only the repository fact.

## 2. Typed reference integrity

`evaluate_reference_integrity` now resolves references by namespace:

| Reference field | Valid namespace |
|-----------------|----------------|
| `dependency_event_ids` | event IDs only |
| `invokes_event_ids` | event IDs only |
| `retries_event_id` | event IDs only |
| `input_artifact_ids` | artifact IDs only |
| `output_artifact_ids` | artifact IDs only |

Invalid references report `{owner, ref_type, target_id}`.

- Wrong-namespace hit (e.g. artifact ref → existing event ID) → `contradicted`
- Missing target → `incomplete`
- Zero required refs → `unavailable` (`value: null`)
- Optional metadata (`model_id` / `tool_id`) never required

Rule ID: `assurance.reference_integrity.v1_1`.

## 3. Consolidation decision: coverage vs integrity

Phase 2.6 exposed `reference_integrity` and `provenance_coverage` with the **same** untyped numerator/denominator (\(r \in K_e \cup K_a\)). That:

1. Double-counted one quantity as two metrics.
2. Incorrectly accepted cross-namespace IDs as “resolved.”

A distinct provenance-coverage property would need additional evidence requirements not present in current records without inventing optional-metadata penalties. **No such defensible distinct measure exists here.**

**Decision:** remove `provenance_coverage`; keep a single typed `reference_integrity` dimension that reports resolution counts and fraction \(C = n_{\mathrm{resolved}}/n\) when \(n>0\). Documentation, calculator, tests, and evaluation summaries updated accordingly. Assurance algorithm version → **`2.6.1`**.

## 4. Attribution sensitivity hardening

`evaluate_attribution_sensitivity` (`assurance.attribution_sensitivity.v1_1`) validates before TV distance:

- P1 result is `P1_DIRECT`; P2 is `P2_ARTIFACT_BRIDGE`
- Same `outcome_id`
- Exact exclusive taxonomy factor keys (no silent zero-fill)
- Finite, non-negative values
- Each vector sums to 1 within \(10^{-9}\)

Identity/missing failures → `unavailable`. Numeric/support failures → `contradicted`.

Formula unchanged: \(\delta = \tfrac12 \sum_f |M_{P1}(f)-M_{P2}(f)|\).

Documented: δ is descriptive allocation sensitivity only — not uncertainty, causal disagreement, or fault probability.

## 5. Completeness / invalidity → status mapping

| Evidence | Status |
|----------|--------|
| Dependency cycle | `trace_completeness` → `contradicted` |
| Unexpected missing parents (completeness report) | `incomplete` |
| Wrong-namespace refs | `reference_integrity` → `contradicted` |
| Missing typed refs | `reference_integrity` → `incomplete` |
| Missing optional metadata | no incompleteness |

Intentional incompleteness is **not** reclassified via ground truth inside the calculator. Overall status uses worst-status precedence, so contradicted/incomplete dimensions prevent overall `verified`.

## 6. Fail-closed evaluation runner

`experiments/scripts/evaluate_assurance_profiles.py`:

- Accounts for every trace directory (or records corpus missing/empty)
- Every trace gets a profile entry or explicit error record
- Writes diagnostics **before** exit
- Any evaluation error → process exit **1**
- Compact outputs under `experiments/results/assurance_phase26/`:
  - `summary.json`
  - `per_trace_status.json`
  - `pilot_diagnostics.json`
  - `fault_matrix_diagnostics.json`

Includes assurance algorithm version, generator version constant, corpus fingerprints, exact command. No huge full-profile dumps.

## 7. Changed files

- `agenttrust/assurance/dimensions.py` — typed integrity; sensitivity/completeness v1_1; coverage removed
- `agenttrust/assurance/calculator.py` — five dimensions; version 2.6.1 wiring
- `agenttrust/assurance/models.py` — `ASSURANCE_ALGORITHM_VERSION = "2.6.1"`
- `agenttrust/__init__.py`, `pyproject.toml` → 2.6.1
- `experiments/scripts/evaluate_assurance_profiles.py` — fail-closed + compact reproducibility
- `tests/unit/test_assurance_profile.py` — adversarial typed-ref / sensitivity / overall-status tests
- `docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md`
- `docs/phase-reports/PHASE_2_6_1_IMPLEMENTATION_REPORT.md` (this file)
- `README.md`

Historical pilot and Phase 2.5.1 fault-matrix corpora **not** modified.

## 8. Verification (executed)

```text
python -m pytest tests -q
# collected 290; passed 290; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0 incomplete=2 pipeline_eligible=66 exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0 fault_types=9 leakage_violations=0 exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# exit 0 (n_errors=0 for both corpora)
```

### Profile counts (algorithm 2.6.1)

| Corpus | Examined | Profiles OK | Incomplete overall | Contradicted overall | Errors |
|--------|----------:|------------:|-------------------:|---------------------:|-------:|
| Historical pilot (2.4.0) | 68 | 68 | 3 | 0 | 0 |
| Fresh strict fault matrix | 10 | 10 | 3 | 0 | 0 |

Sensitivity `unavailable` on 2 traces per corpus (P2 not comparable). Reference integrity `incomplete` on 3 traces per corpus (typed missing refs).

**Not claimed:** final evaluation corpus generation.

## 9. Explicit non-claims / not implemented

- No PLHC / Merkle integrity
- No final evaluation corpus
- No new RPA or MFAV mathematics
- No CTSM / scalar trust score
- No causal attribution
- No commit / push
- Calculator has no ground-truth dependency

## 10. Stop

Phase 2.6.1 complete. Wait for review before further phases.
