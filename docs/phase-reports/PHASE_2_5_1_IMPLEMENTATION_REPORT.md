# PHASE 2.5.1 IMPLEMENTATION REPORT

Close remaining benchmark integrity issues (conflict-label leakage + strict validation modes).

## 1. Starting point

| Item | Value |
|------|--------|
| Branch | `master` |
| Start commit | `583b57ad213c22f219eaa3cc906fd3569d9a3bbe` |
| Working tree | Clean at start |
| Commit/push | **Not performed** |

## 2. Changes

- `faults.py`: conflicting outputs via `decision` + distinct hashes; GT `relation` / `expected_decisions`
- `validation.py`: reject `conflict_label`, `is_conflicting`, etc.
- `validate_phase25_fault_matrix.py`: Mode B strict fresh fault matrix
- `validate_benchmark_pilot.py`: Mode A documentation
- Tests: leakage adversarial + per-fault matrix
- Docs: Phase 2.5 report correction; dataset plan **≈ 1,110**; generator `2.5.1`
- Pilot corpus: **not modified**

## 3. Validation modes

| Mode | Command | Strict fault observables |
|------|---------|--------------------------|
| A Historical pilot | `validate_benchmark_pilot.py --pipeline` | Off (default) |
| B Fresh 2.5.x matrix | `validate_phase25_fault_matrix.py` | On |

## 4. Verification results (executed)

```bash
python -m pytest tests -q
# collected 262; passed 262; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# Mode A: checked=68 failures=0 gt_error_total=0 incomplete=2 pipeline_eligible=66 exit 0
# Note: historical 2.4.0 conflict_label leakage demoted to warnings — not claimed 2.5.1-clean

python experiments/scripts/validate_phase25_fault_matrix.py
# Mode B: checked=10 failures=0 fault_types=9 leakage_violations=0 exit 0
```

| Metric | Value |
|--------|------:|
| Pytest collected / passed | 262 / 262 |
| Historical pilot checked | 68 |
| Historical pilot failures | 0 |
| Pipeline-eligible (Mode A) | 66 |
| Intentionally incomplete | 2 |
| Fresh fault-matrix checked | 10 |
| Fresh fault-matrix failures | 0 |
| Fault types exercised (Mode B) | 9 |
| Leakage violations (Mode B) | 0 |

## 5. Not implemented

Assurance/CTSM, PLHC, final eval corpus, RPA math changes, causal claims, commit/push.
