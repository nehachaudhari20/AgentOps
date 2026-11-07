# Sample-Size and Power Planning (Phase 2.9)

Committed **before** held-out corpus generation. Primary unit = **trace**.

## 1. Prespecified primary endpoint

**Endpoint:** Indicator that an incompleteness-inducing fault pair is distinguished by the evaluation harness using **public observables + Assurance structural dimensions**, without reading planted responsibility:

- Fault member: `incomplete_trace` or `missing_dependency`
- Success criterion (binary): `TraceCompleteness.incomplete == True` on the fault member **and** `incomplete == False` on the matched clean twin (same `matched_pair_id`).

This is a **paired** binary outcome at the pair level.

## 2. Effect size and error rates

| Parameter | Value | Justification |
|-----------|------:|---------------|
| Smallest meaningful effect Δ | 0.20 | Absolute pair-success rate vs a null of uninformative labeling; smaller effects are exploratory |
| α (two-sided) | 0.05 | Conventional |
| Target power | 0.80 (prefer 0.90) | Spec requirement |
| Multiple comparisons | Primary family = 1 contrast; secondary topology/fault contrasts use Benjamini–Hochberg only in exploratory reports | Avoid overclaiming |

## 3. Pilot uncertainty

Historical pilot: 2 intentionally incomplete traces, 66 complete-looking for pipeline eligibility.  
Variance of detection rates is **poorly estimated**. Therefore:

1. Analytic normal approximation is treated as a lower bound check only.
2. **Simulation-based** power (Monte Carlo Bernoulli pairs) is authoritative.
3. Sensitivity: null/control success rate p₀ ∈ {0.50, 0.70, 0.85} with alternative p₁ = min(1, p₀ + Δ).

## 4. Simulation procedure

For proposed pair count n_pairs:

1. Draw n_pairs i.i.d. Bernoulli(p₀) under H₀ and Bernoulli(p₁) under H₁ (independent across pairs for planning; analysis will use McNemar / paired bootstrap on real data).
2. Two-proportion z-test (unpooled) as a conservative planning stand-in; confirm with McNemar when discordant pairs dominate.
3. Power = fraction of 10_000 sims rejecting H₀ at α=0.05.
4. Repeat across p₀ grid and Δ ∈ {0.10, 0.15, 0.20, 0.30}.

Machine-readable results: `data/benchmarks/experimental_2_9/reports/sample_size_power.json` (written by the planning script).

## 5. Chosen N

Held-out incompleteness-relevant pairs:

`2 faults × 6 topologies × 2 scales (S1,S2) × 3 replicates = **72 pairs**` (144 traces).

Simulation (see report) shows power ≥ 0.80 for Δ=0.20 at mid p₀; at p₀=0.85 ceiling effects reduce power for Δ=0.10 — those contrasts remain **exploratory / precision-based**.

Clean-core held-out n=150 supports bootstrap CIs for cell means (5 seeds per topology×scale) without claiming powered multi-way ANOVA.

## 6. Explicit exploratory analyses

- Full 9-fault observability agreement rates
- MFAV vector distances across topologies
- P1/P2 δ

These use precision-based reporting (CI width), not powered superiority claims.

## 7. What we refuse to claim

- That 1,596 traces create external validity.
- That event totals are the sample size.
- That an arbitrary round number is “statistically justified” without the above.
