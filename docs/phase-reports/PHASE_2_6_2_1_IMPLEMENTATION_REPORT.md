# PHASE 2.6.2.1 IMPLEMENTATION REPORT

MFAV conservation integrity closure (event assignments ↔ factor totals).

## 1. Starting branch and commit

| Item | Value |
|------|--------|
| Branch | `master` (no branch created or switched) |
| Start / expected HEAD | `ed69eb1fa667177f4a8a9658d3a040295ab3c344` — Evluation hardening |
| Working tree at start | Clean |
| Commit/push this phase | **Not performed** |

## 2. Objective

Close the remaining MFAV conservation-validation gap from Phase 2.6.2: independently verify that event-level MFAV assignments, raw factor totals, reported total, and reported conservation error agree.

No change to MFAV classification or aggregation mathematics.

## 3. Exact validation logic

Rule ID: `assurance.factor_profile.v1_2`. Algorithm version: **`2.6.2.1`**.

Tolerances (unchanged; not weakened):

| Name | Value |
|------|------:|
| `CONSERVATION_ABS_TOL` | \(10^{-9}\) |
| `REPORT_AGREEMENT_TOL` | \(10^{-9}\) |
| `ALLOCATION_NONNEG_TOL` | \(10^{-12}\) |
| `NORMALIZED_SUM_TOL` | \(10^{-9}\) |

### Event assignments

For every `EventAssignment`:

- Non-empty `event_id`
- `factor` ∈ exclusive taxonomy
- Allocation numeric (not bool), finite, non-negative within float allowance
- No duplicate event IDs
- No assignment silently ignored

\[
T_{\mathrm{events}}=\sum_{e}a(e)
\]

Missing assignment list → `unavailable`. Empty list with \(T_{\mathrm{factors}}>0\) → `contradicted`.

### Raw / reported totals

\[
T_{\mathrm{factors}}=\sum_{f\in F}A_f,\quad
T_{\mathrm{reported}}\approx T_{\mathrm{factors}},\quad
T_{\mathrm{events}}\approx T_{\mathrm{factors}}
\]

### Per-factor aggregation

\[
\forall f:\quad A_f \approx \sum_{e:\operatorname{factor}(e)=f}a(e)
\]

### Conservation error

Aggregator definition: \(\texttt{conservation\_error}=|\texttt{factor\_total}-\texttt{incoming\_total}|\).

Assurance reconstruction from MFAVResult alone:

\[
\epsilon_{\mathrm{MFAV}}=\lvert T_{\mathrm{factors}}-T_{\mathrm{events}}\rvert
\]

Reported `conservation_error` must agree with \(\epsilon_{\mathrm{MFAV}}\) within `REPORT_AGREEMENT_TOL`. For COMPLETE: \(\epsilon_{\mathrm{MFAV}}\le 10^{-9}\).

Missing evidence is never replaced with zero. `MFAVStatus.COMPLETE` alone is insufficient. ZERO_ALLOCATION / UNDEFINED remain `unavailable`.

## 4. Files changed

- `agenttrust/assurance/dimensions.py` — event-assignment / aggregation / ε checks
- `agenttrust/assurance/models.py` — version `2.6.2.1`
- `agenttrust/__init__.py`, `pyproject.toml` → `2.6.2.1`
- `tests/unit/test_assurance_validation_262.py` — adversarial assignment tests + valid helper
- `tests/unit/test_assurance_profile.py` — version assert
- `docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md`
- `docs/phase-reports/PHASE_2_6_2_IMPLEMENTATION_REPORT.md` — repository-history correction
- `docs/phase-reports/PHASE_2_6_2_1_IMPLEMENTATION_REPORT.md` (this file)
- `README.md`

## 5. Tests added

Adversarial cases: missing / empty+positive assignments; duplicate event IDs; unknown factor; NaN/±inf/negative event allocation; event sum ≠ raw total; per-factor mismatch with matching totals; one-factor swap; reported ε disagreement; tampered assignments; tampered raw; pipeline MFAV verified; incomplete/overridden incomplete; zero/undefined unavailable.

## 6. Verification (actual runs)

```text
python -m pytest tests -q
# collected 353; passed 353; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0 incomplete=2 pipeline_eligible=66; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0 fault_types=9 leakage_violations=0; exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# assurance_algorithm_version=2.6.2.1; pilot 68/68; matrix 10/10; n_errors=0; exit 0
```

| Corpus | Examined | Profiles OK | Incomplete overall | Errors |
|--------|----------:|------------:|-------------------:|-------:|
| Historical pilot | 68 | 68 | 3 | 0 |
| Fresh strict fault matrix | 10 | 10 | 3 | 0 |

## 7. Remaining limitations

- Calculator still does not see original RPA `incoming_total` directly; it reconstructs conservation from assignments vs factors (valid when every consumed RPA node is one assignment, as produced by the aggregator).
- Intentional incompleteness remains evaluation-side.
- No PLHC / trust score / causal claims.
- Historical corpora unmodified.

## 8. Stop

- Working tree: dirty (2.6.2.1 uncommitted).
- No branch created or switched.
- No commit or push performed.
- STOP after Phase 2.6.2.1 — wait for review before PLHC.
