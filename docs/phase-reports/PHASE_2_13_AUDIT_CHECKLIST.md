# Phase 2.13 Audit Checklist

**Start HEAD:** `242d628b900ebcc599d07a7decbdb4de5eaec211`  
**Branch:** `master` (clean)

| # | Issue | Affected files | Tests / validators |
|---|-------|----------------|--------------------|
| 1 | Power sim uses independent two-proportion z-test; design is paired | `agenttrust/benchmark/dataset/power.py`, `SAMPLE_SIZE_AND_POWER.md`, `EXPERIMENTAL_DATASET_DESIGN.md`, power JSON | `tests/unit/test_power_213.py` |
| 2 | Equal-root GT aligned with RPA α=0 → MAE≈0 non-discriminative | `attribution_reference.py`, `gt_access.py`, `compare.py`, `rq_analysis.py`, baseline protocol | `tests/unit/test_attribution_gt_213.py` |
| 3 | P2 bridge subgroup empty / insufficient distinct lineage | `projections.py`, benchmark topologies/generator, new corpus block | `tests/unit/test_artifact_bridge_213.py` |
| 4 | RQ1 overstated as independent lineage recovery | `rq_analysis.py`, FINAL_EVALUATION_REPORT, claim matrix | RQ1 negative-case tests |
| 5 | RQ4 only incompleteness | `rq_analysis.py` | Assurance observability tests |
| 6 | RQ5 first-N=50, no CIs/sampling design | `rq_analysis.py`, `plhc_attacks.py` | Stratified PLHC tests |
| 7 | Cliff’s δ unpaired for paired contrasts | `metrics.py`, SAP | Paired effect-size tests |
| 8 | First-N selection bias RQ4/RQ5 | `rq_analysis.py` | Deterministic sampling tests |
| 9 | `experiments/results/*` ignored; reproduce skips stats as success | `.gitignore`, `reproduce.py`, REPRODUCIBILITY.md | `test_reproduce_213.py` |
| 10 | Claim language vs evidence | docs/results/*, README, PHASE_2_FINAL | Claim–evidence matrix 2.13 |

**Preservation:** Phase 2.9 corpus frozen. New materials versioned under `experimental_2_13_*` / `results/phase_2_13/`.
