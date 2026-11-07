# Phase 2.13 Implementation Report

## Repository state

| Item | Value |
|------|--------|
| Branch | `master` only |
| Initial HEAD | `242d628b900ebcc599d07a7decbdb4de5eaec211` |
| Final HEAD | `242d628b900ebcc599d07a7decbdb4de5eaec211` (unccommitted Phase 2.13 changes; **no commit/push**) |
| Working tree at start | Clean |

## Algorithms / modules changed

| Area | Change |
|------|--------|
| `power.py` | Paired McNemar simulation; invalid independent API raises |
| `attribution_reference.py` | Alignment disclosure; `intervention_participation_mass.v1` |
| `bridge_scenarios.py` | **New** versioned P1/P2-differentiating corpus |
| `sampling.py` | **New** stratified deterministic sampling + Wilson CI |
| `metrics.py` | Paired Cliff’s δ, paired d, confusion rates, finite validation |
| `rq_analysis.py` | RQ1 wording + negatives; RQ4 observability; RQ5 stratified+CI; RQ2/3 disclosures |
| `plhc_attacks.py` | Expanded attack classes |
| `gt_access.py` | Intervention reference accessor |
| `reproduce.py` | Classification; mandatory skip ≠ success |
| `.gitignore` | Allow compact `phase_2_13/` evidence |
| `check_repeatability.py` | Assurance profile included |

## Dataset versions

| Dataset | Action |
|---------|--------|
| `experimental_2_9` | **Preserved** (no silent regeneration) |
| `sample_size_power_2_13.json` | **Added** corrected paired power |
| `experimental_2_13_bridges` | **Created** (6 scenarios) |

## Statistical methods used

McNemar exact / discordant binomial power; stratified sampling; bootstrap mean CIs; paired mean-diff CI; paired Cliff’s δ; paired standardized mean diff; Wilson binomial CIs; Holm correction helper; confusion rates; edge P/R/F1.

## Tests actually executed

```text
python -m pytest tests -q
→ 488 tests collected/passed (exit 0)
```

Plus Phase 2.13 unit module `tests/unit/test_phase_2_13.py` (paired power, GT, bridges, sampling, PLHC, reproduce semantics).

## Validators / scripts executed

| Command | Result |
|---------|--------|
| `validate_phase_2_13.py` | OK (power primary=0.3816; bridges n=6) |
| `validate_benchmark_pilot.py --pipeline` | checked=68 failures=0 |
| `validate_phase25_fault_matrix.py` | failures=0 |
| `validate_plhc.py` | n_errors=0 (pilot+fault matrix) |
| `evaluate_assurance_profiles.py` | n_errors=0 |
| `validate_experimental_dataset.py` | ok; n_traces=1596 |
| `check_repeatability.py` | ok; n_diffs=0 |
| `run_final_evaluation.py` (heldout; skip-rerun comparison) | wrote `experiments/results/phase_2_13/` |

## Evaluation results (summary)

- Paired power @72: **0.3816** (does **not** meet 80%); suggested n≈**176**; corpus not regenerated.
- RQ1: fidelity high; explicitly not real-world recovery.
- RQ2 equal-root: MAE≈0 (aligned); intervention sample: RPA MAE≈0.45 (n_defined=14/80).
- RQ3: Δ=0; bridge edges counted in 2.9 paired rows = **0**.
- Bridge corpus: all positive/negative expectations met; P1/P2 differ when constructed.
- RQ4/RQ5: stratified n=120 / n=80 with manifests and CIs.

## Failed or skipped stages

- Full comparison re-computation across all splits: **skipped** (`--skip-rerun-comparison`); reused Phase 2.10 comparison JSON for RQ2/RQ3 aggregates.
- Full held-out intervention scoring over all fault traces: **not** run (stratified n=80 only).
- Corpus regeneration to n≈176 pairs: **not** run (requires explicit approval).

## Remaining limitations

See `docs/results/PHASE_2_13_RESEARCH_VALIDITY_REPORT.md`.

## Reproduction commands

```bash
python -m pytest tests -q
python experiments/scripts/validate_phase_2_13.py
python experiments/scripts/reproduce.py --all-safe
python experiments/scripts/reproduce.py --complete   # full evaluation path
```

## Deliverables checklist

1. `docs/phase-reports/PHASE_2_13_IMPLEMENTATION_REPORT.md` — this file  
2. `docs/results/PHASE_2_13_RESEARCH_VALIDITY_REPORT.md`  
3. `docs/results/PHASE_2_13_CLAIM_EVIDENCE_MATRIX.md`  
4. Updated SAP / sample-size / dataset / baseline / threat / repro docs  
5. `sample_size_power_2_13.json` + bridge corpus  
6. `experiments/results/phase_2_13/` (+ run manifest)  
7. `experiments/scripts/validate_phase_2_13.py`  
8. Updated README + claim matrix  
9. Audit checklist: `docs/phase-reports/PHASE_2_13_AUDIT_CHECKLIST.md`  

**Stop condition:** Phase 2.13 complete; no Phase 2.14; no commit/push unless authorized.
