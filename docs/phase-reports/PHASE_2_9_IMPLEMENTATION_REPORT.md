# PHASE 2.9 IMPLEMENTATION REPORT

Benchmark expansion and experimental dataset construction.

## 1. Starting branch and HEAD

| Item | Value |
|------|--------|
| Branch | `master` (no branch created or switched) |
| Start HEAD | `a63f1ab21979b65062ffeba66f5e34bc7286dc30` — Integrate framework (Phase 2.8 present) |
| Working tree at start | Clean |
| Commit/push this phase | **Not performed** |
| End HEAD (unchanged) | `a63f1ab21979b65062ffeba66f5e34bc7286dc30` |

## 2. What was delivered

1. Binding design: `docs/methodology/EXPERIMENTAL_DATASET_DESIGN.md`
2. Sample-size / power plan: `docs/methodology/SAMPLE_SIZE_AND_POWER.md` + machine-readable `reports/sample_size_power.json`
3. Dataset package `agenttrust/benchmark/dataset/` (design, seeds, attribution reference, observability, power, corpus, validation)
4. Generators/validators:
   - `experiments/scripts/generate_experimental_dataset.py`
   - `experiments/scripts/validate_experimental_dataset.py`
5. Generated corpus under `data/benchmarks/experimental_2_9/` with isolated splits
6. Reports: statistics, split coverage, GT validation, fault observability matrix, fingerprints
7. Tests: `tests/unit/test_experimental_dataset_29.py`

## 3. Historical pilot vs experimental corpus

| Corpus | Traces | Role |
|--------|-------:|------|
| `data/benchmarks/pilot/` (gen 2.4.0) | 68 | Historical implementation pilot — **not** held-out final eval |
| `experimental_2_9/development` | 276 | Dev tooling / pipeline iteration |
| `experimental_2_9/validation` | 522 | Validation |
| `experimental_2_9/heldout_test` | 798 | Frozen held-out evaluation |
| **Phase 2.9 total** | **1,596** | Independent **trace** units |

Nested event volume across experimental splits: **205,974** (not an independent sample size).

## 4. Design summary

- Factors: topology (6), scenario (rotated), scale S1–S5, 9 fault families + clean, matched clean/fault pairs.
- Fault block restricted to S1[/S2]; S3–S5 faults omitted (documented gap).
- Seed bands: dev 10k–19k, val 20k–29k, test 30k–39k; disjoint from pilot seeds ≤200.
- Primary powered contrast: incompleteness pair detection Δ=0.20, α=0.05, held-out 72 pairs; simulated primary cell power ≈ **0.869** (p₀=0.70).

## 5. Ground truth

- Version `gt-2.9.0`
- Attribution reference method `equal_root_ancestor_mass.v1` — independent of ConservedRPA/MFAV
- Stored only under `ground_truth/`; leakage scanners on algorithm inputs
- Fault observability matrix declares which faults are directly observable / require GT / not reliably detectable

## 6. Generation result (actual)

```text
python experiments/scripts/generate_experimental_dataset.py --root data/benchmarks/experimental_2_9 --force
# development: planned=276 written=276 failed=0
# validation:  planned=522 written=522 failed=0
# heldout_test: planned=798 written=798 failed=0
# any_fail=false; exit 0
```

```text
python experiments/scripts/validate_experimental_dataset.py
# ok=true; n_traces=1596; cross-split seed/pair overlap empty; exit 0
```

Corpus fingerprints (SHA-256 prefixes):

| Split | n | corpus_fingerprint_sha256 (prefix) |
|-------|--:|-------------------------------------|
| development | 276 | `24e0609703d78928…` |
| validation | 522 | `c9277e4db0af11ab…` |
| heldout_test | 798 | `a45124696b8ec089…` |

Full digests in each split’s `fingerprint_manifest.json`.

## 7. Tests and regression suite (actual)

```text
python -m pytest tests -q
# 464 collected; all passed; exit 0
```

```text
python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0; exit 0

python experiments/scripts/validate_plhc.py
# pilot 68/68; fault_matrix 10/10; exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# pilot+matrix n_errors=0; exit 0
```

## 8. Known limitations

- Scenario×topology is rotated, not a full cross in the clean core.
- Faults at S3–S5 are out of the primary matrix.
- Attribution reference is structural equal-root share — **not** causal GT.
- Pilot variance for power planning is weak (2 incomplete traces); sensitivity grid documented.
- Baselines / ablations deferred to later phases (not started).

## 9. Incomplete work

None for Phase 2.9 scope. Phase 2.10 not started. No commit/push performed.
