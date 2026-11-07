# Statistical Analysis Plan (Phase 2.11 + 2.13 correction)

Trace = primary experimental unit. Matched pairs remain paired. Events/artifacts are never independent N.

## Research questions (corrected wording)

| RQ | Question | Primary outcome |
|----|----------|-----------------|
| RQ1 | Fidelity of MLPG reconstruction vs **simulator-declared** lineage | Edge P/R/F1 (DEPENDS_ON; PRODUCES/CONSUMES) |
| RQ2 | RPA vs attribution references | MAE vs equal-root (**aligned**) and intervention-participation (independent when defined) |
| RQ3 | P2 vs P1 improvement | Paired Δ = MAE(P2)−MAE(P1); bridge-eligible subgroup required for interpretation |
| RQ4 | Assurance **diagnostics** (not comprehensive fault detection) | Completeness endpoint + observability-aware rates |
| RQ5 | PLHC tamper-evidence vs retained checkpoint | Stratified detection rates + Wilson 95% CIs; clean FRR |

## Experimental unit and inclusion

- Unit: one trace (or one matched pair for incompleteness).
- Inclusion: catalog membership; stratified deterministic sampling (not first-N).
- Exclusion: missing GT; method `ineligible`/`failed`; `not_reliably_detectable` faults excluded from ordinary Assurance FN denominators — all recorded.

## Metrics

`agenttrust/evaluation/metrics.py`: MAE, RMSE, Spearman, top-k, TV, edge P/R/F1, bootstrap CIs, **paired** Cliff’s δ, paired standardized mean difference, Holm correction, confusion rates. Empty-set and tie handling documented in code/tests.

## Inference

- Trace-level percentile bootstrap 95% CIs (seed documented).
- Paired bootstrap for paired contrasts.
- McNemar / exact binomial for paired incompleteness.
- Confirmatory family: primary incompleteness McNemar; Holm if multiple confirmatory p-values.
- Exploratory analyses explicitly labeled (topology/scale/bridge subgroups; unpaired Cliff’s δ only as exploratory).
- Do not treat inferential agreement against a structurally identical reference as independent accuracy without disclosure.

## Sampling (Phase 2.13)

`agenttrust/evaluation/sampling.py`: deterministic stratified sampling by fault family × topology × scale × clean/fault. Manifest records population IDs, selected IDs, seed, stratum coverage.

## Missing data

Report `n_eligible`, `n_scored`, `n_excluded`, `n_undefined` with reasons. No silent discard of failed methods. No imputation of allocations.

## Practical significance (prespecified)

- RQ3: \|mean Δ\| ≥ 0.02 MAE as smallest interesting difference.
- RQ5: report detection with CIs; do not claim immutability.

## Limitations

- Equal-root GT structurally aligned with RPA α=0.
- Intervention GT undefined on clean traces; not causal/legal responsibility.
- B2 alias of RPA-P1; B3 Markov not independently implemented.
- RQ1 synthetic oracle ≠ production lineage recovery.
- RQ4 incompleteness + observability diagnostics ≠ broad fault detection.
- Phase 2.9 independent-Bernoulli power superseded by paired McNemar simulation.
