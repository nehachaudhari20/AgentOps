# Final Evaluation Report (Phase 2.11 + 2.13 validity correction)

Machine-readable sources: `experiments/results/final_evaluation/` (historical), `experiments/results/phase_2_10/`, and **`experiments/results/phase_2_13/`** (corrected protocols).  
Confirmatory split: **`heldout_test`** (n_examined=798 traces; n_failed=0).  
Experimental unit: **trace**. Event totals are not N.

Dataset fingerprint (held-out corpus): see `heldout_test_rq_summary.json` → `dataset_fingerprint` (matches Phase 2.9 `fingerprint_manifest.json`).

**Phase 2.13 protocol changes (do not rewrite historical JSON):** paired McNemar power; stratified RQ4/RQ5 sampling; observability-aware Assurance; expanded PLHC attacks with CIs; intervention attribution reference; versioned bridge corpus; reproduction cannot fake success on skipped mandatory stages.

---

## RQ1 — MLPG reconstruction fidelity (simulator-declared lineage)

**Question.** Fidelity of MLPG reconstruction against **simulator-declared** lineage.

**Not claimed.** Independent real-world lineage recovery.

**Method.** Edge precision/recall/F1 of MLPG relationships vs GT `expected_relationships` (DEPENDS_ON, PRODUCES, CONSUMES). Negative relationship diagnostics in Phase 2.13 evaluator.

**Data.** Held-out 798 traces (historical aggregate; Phase 2.13 uses stratified sampling when limited).

| Relation | Mean F1 | 95% CI (bootstrap) | n |
|----------|--------:|--------------------|--:|
| DEPENDS_ON | 0.9994 | [0.9993, 0.9996] | 798 |
| PRODUCES | 1.0000 | [1.0000, 1.0000] | 798 |
| CONSUMES | 1.0000 | [1.0000, 1.0000] | 798 |

**Verdict: Supported by the evaluated benchmark** for observable lineage reconstruction.  
**Limitation:** This is graph-construction fidelity, not causal inference.

---

## RQ2 — Responsibility attribution accuracy

**Question.** How close is ConservedRPA (and baselines) to independent planted agent reference (`equal_root_ancestor_mass.v1`)?

**Method.** MAE (union agent support) with bootstrap CIs. Online vs offline methods separated.

**Held-out (primary):**

| Method | Budget | Mean MAE | 95% CI | n_scored |
|--------|--------|---------:|--------|---------:|
| rpa_p1 | online | 0.000 | [0, 0] | 738 |
| rpa_p2 | online | 0.000 | [0, 0] | 738 |
| B2_p1_equal_share (alias) | alias | 0.000 | [0, 0] | 738 |
| B0_uniform_agent | online | 0.234 | [0.228, 0.239] | 798 |
| B1_last_touch | online | 0.655 | [0.622, 0.687] | 798 |
| B4_shapley | offline | — | — | 0 (not run in bulk) |

**Verdict: Partially supported / limited.**  
RPA α=0 matches this synthetic reference with MAE≈0 on scored traces because **equal-root ancestor mass is structurally aligned with equal-parent reverse flow** on these generator DAGs. That demonstrates consistency with the chosen reference, **not** causal or legal accuracy, and **weakens discriminative power** of RQ2 for claiming superiority of RPA over equally root-aligned rules. B0/B1 are clearly worse under this reference.

Excluded: 798−738=60 traces without successful RPA scoring (ineligible/incomplete/failed) — retained in denominators via comparison artifacts.

---

## RQ3 — Artifact-aware attribution (P2 vs P1)

**Primary contrast.** Δ = MAE(P2) − MAE(P1), paired.

| Quantity | Value |
|----------|------:|
| n_paired | 738 |
| mean Δ | 0.000 |
| 95% CI | [0, 0] |
| Cliff’s δ | 0.000 |
| Practical threshold \|Δ\| | 0.02 |
| Subgroup with counted artifact-bridge edges | n=0 in paired rows |

**Verdict: Not supported (no measured improvement) under this reference and corpus.**  
P2 did not reduce MAE vs P1. In this generator, artifact bridges are often already represented as DEPENDS_ON (deduplicated), so P2 adds no agent-mass change against equal-root GT.  
**Do not claim improvement from additional edges alone.**

---

## RQ4 — Assurance Profile diagnostics

**Method (historical first-N sample).** `trace_completeness` incomplete/contradicted vs GT `intentionally_incomplete` (sample n=100 held-out).

| TP | FP | TN | FN | Detection rate | False-alarm rate |
|---:|---:|---:|---:|---------------:|-----------------:|
| 8 | 0 | 91 | 1 | 0.889 | 0.000 |

**Phase 2.13:** stratified sampling; separate completeness endpoint; observability-aware eligibility (`directly_observable` / `indirect_inconsistency` / `requires_ground_truth` / `not_reliably_detectable`); confusion metrics + Wilson CIs. See `phase_2_13` RQ4 outputs.

**Verdict: Partially supported** for incompleteness signaling.  
**Not claimed:** comprehensive fault detection, fraud detection, or trustworthiness scoring.  
**Caveat:** `not_reliably_detectable` faults are excluded from ordinary Assurance FN denominators.

---

## RQ5 — PLHC integrity verification

**Method (historical first-N).** Controlled attacks vs retained genesis checkpoint (n=50 held-out).

| Check | Rate |
|-------|-----:|
| Clean verified | 1.00 |
| False reject | 0.00 |
| event_payload_change detected | 1.00 |
| artifact_content_change detected | 1.00 |
| leaf_removal / equivalent mutate detected | 1.00 |
| checkpoint_alteration detected | 1.00 |

**Phase 2.13:** stratified sampling; expanded attack classes (artifact deletion, relationship modification, reordering via timestamps, identity substitution, checkpoint chain); per-attack Wilson 95% CIs; sampling manifest.

**Verdict: Supported** under the declared threat model (**tamper-evident vs retained checkpoint**).  
**Not claimed:** immutability, external anchoring, or dual-rewrite resistance.

---

## Cross-cutting limitations

1. Synthetic equal-root GT is too close to ConservedRPA α=0 for strong RQ2/RQ3 discrimination.
2. B3 Markov not independently implemented (documented equivalence).
3. Shapley omitted from bulk confirmatory tables (offline; enable separately).
4. RQ4 uses a sampled incompleteness contrast, not all nine fault families as detection targets.
5. No algorithm changes were made to improve held-out numbers.

## Bottom line (honest)

| RQ | Conclusion |
|----|------------|
| RQ1 | Supported |
| RQ2 | Partially supported / reference-limited |
| RQ3 | Not supported (null Δ) |
| RQ4 | Partially supported (incompleteness) |
| RQ5 | Supported (local tamper-evidence) |
