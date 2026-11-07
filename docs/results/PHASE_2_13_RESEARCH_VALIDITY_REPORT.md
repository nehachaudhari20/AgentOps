# Phase 2.13 Research Validity Report

**Branch:** `master`  
**Start HEAD:** `242d628b900ebcc599d07a7decbdb4de5eaec211`  
**Priority:** scientific correctness over impressive metrics.

## A. Implemented and tested capabilities

- Paired McNemar / discordant-binomial power simulation (`power.py` 2.13.0).
- Intervention participation attribution reference (`intervention_participation_mass.v1`).
- Artifact-bridge scenarios with P1≠P2 by construction (`experimental_2_13_bridges`).
- Stratified deterministic sampling; Wilson CIs; paired effect sizes; Holm helper.
- Observability-aware Assurance RQ4; expanded PLHC attack catalog for RQ5.
- Reproduction runner classifications; mandatory-skip non-zero exit.

## B. Empirically evaluated (Phase 2.13 held-out)

| RQ | Sample | Key result |
|----|--------|------------|
| RQ1 | n=798 (full held-out) | DEPENDS_ON F1≈0.999; PRODUCES/CONSUMES F1=1.0 — **simulator fidelity** |
| RQ2 equal-root | n_scored=738 (reused 2.10 comparison) | RPA MAE≈0 — **aligned reference** |
| RQ2 intervention | stratified n=80 → 14 defined | RPA MAE≈0.45; B0≈0.21; B1≈0.64 — **not zero** |
| RQ3 | n_paired=738; bridge edges=0 in 2.9 | Δ=0 — **no P2 MAE improvement** |
| RQ4 | stratified n=120 | Completeness diagnostic endpoint + observability tables |
| RQ5 | stratified n=80 | Per-attack detection with Wilson CIs; threat model scoped |

Machine-readable: `experiments/results/phase_2_13/`.

## C. Synthetic-only evidence

All experimental corpus results are synthetic generator traces. Bridge corpus is synthetic by design. Intervention labels are planted simulator semantics.

## D. Inconclusive findings

- **Attribution accuracy vs causal truth:** cannot be conclusively answered; equal-root is aligned; intervention reference has limited defined N and is not causal.
- **P2 superiority:** graph differentiation demonstrated on bridge corpus; MAE superiority not demonstrated on Phase 2.9 held-out under equal-root GT.
- **Primary incompleteness power:** at n=72 pairs, primary-cell paired power ≈ **0.3816** (not ≥0.80). Suggested n≈**176** pairs; corpus **not** regenerated.

## E. Explicitly unsupported claims

- Independent real-world lineage recovery (RQ1).
- Independent attribution accuracy from MAE≈0 vs equal-root.
- P2 superiority on Phase 2.9 MAE.
- Comprehensive Assurance fault detection.
- PLHC immutability / external anchoring / dual-rewrite resistance.
- Agent trustworthiness, legal liability, causality, production validity.

## F. Remaining limitations

- Phase 2.9 topologies co-emit DEPENDS_ON with artifact consume → empty bridge subgroup.
- Pilot joint incompleteness rates poorly estimated → power grid sensitivity.
- B2 alias of RPA-P1; B3 Markov not independent.
- Full comparison re-run skipped (`--skip-rerun-comparison`); RQ2/RQ3 aggregates reuse Phase 2.10 comparison JSON with updated analysis code for disclosures/paired stats.
- Intervention eval on stratified subset (80), not full held-out fault population.

## Power correction (detail)

Invalid Phase 2.9 independent z-test power≈0.8691 superseded. Corrected report: `data/benchmarks/experimental_2_9/reports/sample_size_power_2_13.json`. Historical corpus preserved; regeneration plan requires explicit approval (suggested ≈176 pairs under primary cell).
