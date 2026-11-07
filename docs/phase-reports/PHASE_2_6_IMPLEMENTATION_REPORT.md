# PHASE 2.6 IMPLEMENTATION REPORT

Evidence-bounded Assurance Profile.

## 1. Starting commit and branch

| Item | Value |
|------|--------|
| Branch | `master` |
| Start commit | `39eb02d5d7c6ab36ee62cbcd3bc53386d8204bb8` — Close benchmark integrity issue |
| Commit/push | **Not performed** |

## 2. Pre-implementation hardening

`validate_phase25_fault_matrix.py` now **hard-fails** (exit 2) before generation when runtime generator version ≠ `GENERATOR_VERSION`. Unit test covers mismatch.

## 3. Architecture summary

Package `agenttrust/assurance/`:

| Module | Role |
|--------|------|
| `models.py` | Status vocabulary + precedence |
| `dimensions.py` | Six dimension evaluators |
| `calculator.py` | `AssuranceProfileCalculator` |
| `result.py` | `DimensionResult`, `AssuranceProfile` |
| `report.py` | Serialization helpers |

Design: `docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md`

## 4. Mathematical definitions (summary)

- **Reference integrity / coverage:** \(C = n_{\mathrm{ok}}/n\) over required dependency/invoke/retry/artifact refs; \(n=0\) → `unavailable` (no invented value).
- **Attribution computability:** RPA conservation abs error ≤ \(10^{-9}\), no cycle; overridden/incomplete → `incomplete`.
- **Attribution sensitivity:** \(\delta=\frac12\sum_f |M^{P1}_f-M^{P2}_f|\) when both MFAV normalized vectors defined for the same outcome.
- **Factor profile:** embeds MFAV raw/normalized allocations; no trust score / entropy-as-trust.

## 5. Changed files

- `agenttrust/assurance/*` (new implementation)
- `agenttrust/__init__.py`, `pyproject.toml` → 2.6.0
- `experiments/scripts/validate_phase25_fault_matrix.py` (version hard-fail)
- `experiments/scripts/evaluate_assurance_profiles.py`
- `tests/unit/test_assurance_profile.py`
- `docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md`
- `docs/phase-reports/PHASE_2_6_IMPLEMENTATION_REPORT.md`
- `README.md`

Historical pilot and Phase 2.5.1 fault-matrix corpora **not** rewritten.

## 6. Verification (executed)

```bash
python -m pytest tests -q
# collected 273; passed 273; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0 incomplete=2 pipeline_eligible=66 exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0 fault_types=9 leakage_violations=0 exit 0

python experiments/scripts/evaluate_assurance_profiles.py
```

| Corpus | Examined | Profiles OK | Incomplete overall | Errors | Notes |
|--------|----------:|------------:|-------------------:|-------:|-------|
| Historical pilot | 68 | 68 | 3 | 0 | sensitivity unavailable on 2 traces |
| Phase 2.5.1 fault matrix | 10 | 10 | 3 | 0 | sensitivity unavailable on 2 traces |

Outputs under `experiments/results/assurance_phase26/`.

## 7. Explicit non-claims / not implemented

- No CTSM trust score; no PLHC; no final eval corpus; no RPA/MFAV math changes; no causal/legal claims; no GT inside calculator; no commit/push.

## 8. Limitations / unresolved

- Intentional vs unexpected incompleteness is evaluation-side (GT annotation), not calculator-side.
- Sensitivity requires caller-supplied P1/P2 MFAV pairs (unavailable when P2 RPA fails).
- No cryptographic integrity dimension until PLHC.
- Wait for review before Phase 2.7.
