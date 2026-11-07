# Statistical Analysis Plan (Phase 2.11)

Committed before confirmatory held-out aggregation. Trace = primary experimental unit.

## Research questions

| RQ | Question | Primary outcome |
|----|----------|-----------------|
| RQ1 | MLPG fidelity vs GT lineage | Edge F1 (DEPENDS_ON; PRODUCES/CONSUMES) |
| RQ2 | RPA vs independent agent reference | MAE / RMSE / Spearman / top-1 |
| RQ3 | P2 vs P1 improvement | Paired Δ = MAE(P2)−MAE(P1) |
| RQ4 | Assurance diagnostics | Dimension TP/FP rates vs observability matrix |
| RQ5 | PLHC tamper detection | Detection rate by attack class; clean FRR |

## Experimental unit and inclusion

- Unit: one trace (or one matched pair for incompleteness).
- Events/artifacts/agents nested in a trace are **not** independent samples.
- Inclusion: catalog membership in the target split; method-specific eligibility recorded.
- Exclusion: missing GT attribution reference; method `ineligible`/`failed` — counted in denominators, not silently dropped.

## Metrics

Defined in `agenttrust/evaluation/metrics.py` with empty-set rules and tests.

## Inference

- Trace-level percentile bootstrap 95% CIs for means (seed documented).
- Paired bootstrap for RQ3 Δ.
- Effect size: Cliff’s δ for directional contrasts; report mean/median Δ.
- Confirmatory family (held-out): RQ3 primary paired contrast; Holm adjustment if multiple confirmatory p-values are reported.
- Subgroup (topology/scale/bridge) analyses are **exploratory** unless pre-powered.

## Missing data

Report `n_eligible`, `n_scored`, `n_excluded` with reasons. No imputation of allocations.

## Practical significance (prespecified)

- RQ3: |mean Δ| ≥ 0.02 MAE absolute as smallest interesting difference (exploratory sensitivity also at 0.01 / 0.05).
- RQ5: detection rate ≥ 0.95 on defined attacks; clean false-reject = 0 on controls.

## Limitations

- Synthetic GT equal-root share ≠ causal truth.
- B2 alias of RPA-P1; B3 not independent.
- Shapley uses reachability game (offline combinatorial).
- Assurance cannot detect fundamentally unobservable faults.
- Pilot power uncertainty carried from Phase 2.9.
