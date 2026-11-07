# Sample-Size and Power Planning (Phase 2.13 correction)

Primary unit = **trace** (matched clean/fault **pair** for the primary incompleteness endpoint).

## 1. Prespecified primary endpoint

**Endpoint:** Matched-pair binary contrast for incompleteness-inducing faults
(`incomplete_trace` / `missing_dependency`) vs clean twin (same `matched_pair_id`).

**Test:** Exact McNemar / binomial test on discordant pairs  
H₀: P(fault-only success) = P(clean-only success) among discordant pairs.

This replaces the Phase 2.9 planning stand-in that simulated **independent** Bernoulli groups with an unpooled two-proportion z-test. That figure (power ≈ 0.8691 at 72 pairs) is **invalid** for the paired design and must not be cited.

## 2. Joint outcome model

Each pair is drawn from a 4-cell multinomial:

| Cell | Meaning |
|------|---------|
| both | fault and clean both “succeed” on the endpoint |
| fault_only | fault succeeds, clean fails |
| clean_only | clean succeeds, fault fails |
| neither | neither succeeds |

Power simulations use `agenttrust/benchmark/dataset/power.py` (`simulate_paired_power`, ≥10_000 sims, fixed seeds).

## 3. Sensitivity grid and decision

Machine-readable: `data/benchmarks/experimental_2_9/reports/sample_size_power_2_13.json`  
(Historical `sample_size_power.json` preserved if present; do not treat it as valid paired evidence.)

Primary planning cell: discordant rate 0.30, discordant asymmetry 0.40.

- If primary-cell power ≥ 0.80 at n=72 → retain held-out incompleteness pair count.
- Otherwise → report suggested n for 80% and **do not silently regenerate** the Phase 2.9 corpus; regeneration requires explicit approval.

## 4. Chosen N (catalog preserved) and 2.13 decision

Held-out incompleteness-relevant pairs remain:

`2 faults × 6 topologies × 2 scales (S1,S2) × 3 replicates = **72 pairs**` (144 traces).

**Phase 2.13 paired simulation (10_000 sims):** primary-cell power at n=72 ≈ **0.3816** (does **not** meet 0.80). Suggested n_pairs ≈ **176** under the same primary joint cell. Historical Phase 2.9 corpus is **preserved**; regeneration requires explicit approval (not auto-run).

## 5. Exploratory analyses (not powered superiority claims)

- Full 9-fault observability agreement rates
- MFAV vector distances across topologies
- P1/P2 δ (requires bridge-eligible traces; see `experimental_2_13_bridges`)

## 6. What we refuse to claim

- That independent two-proportion power justifies the paired design.
- That 1,596 traces create external validity.
- That event totals are the sample size.
- 80%/90% power unless the paired simulation supports it.
