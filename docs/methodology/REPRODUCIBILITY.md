# Reproducibility instructions (Phase 2.13)

## Clean-environment guide

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python experiments/scripts/reproduce.py --complete
```

`--complete` runs full evaluation + Phase 2.13 validator. A skipped mandatory stage **cannot** report complete success (non-zero exit).

## Classification

| Class | Meaning |
|-------|---------|
| `complete_reproduction` | Required stages OK including full evaluation / phase_2_13 |
| `smoke_test` | Pipeline/baselines smoke only |
| `partial_reproduction` | Some mandatory artifacts missing or soft-skipped |
| `failed_reproduction` | Stage failure |

`--smoke` may soft-skip missing frozen stats artifacts but still exits non-zero (partial).

## Stage reference

| Stage | Notes |
|-------|-------|
| env | Import smoke |
| dataset_validate | Experimental 2.9 catalogs |
| dataset_regenerate | Explicit `--regenerate-dataset` only |
| pipeline / baselines | Smoke paths under `repro_scratch/` |
| stats | Requires frozen comparison or phase_2_13 results |
| full_evaluation | Writes `experiments/results/phase_2_13/` |
| repeatability | Fingerprints, RPA, MFAV, PLHC, Assurance |
| tests / validators / phase_2_13 | pytest + validators |

## Preserved results

Compact Phase 2.13 evidence under `experiments/results/phase_2_13/` is intentionally trackable (`.gitignore` exceptions). Large comparison JSON under `phase_2_13/comparisons/` remains ignored. Historical `phase_2_10` / `final_evaluation` stay gitignored; regenerate locally as needed.

## Determinism

Fixed seeds + frozen inputs → bit-identical provenance fingerprints, RPA/MFAV, PLHC roots, Assurance profiles (floats within `1e-12`). Wall-clock excluded from content hashes.

## Dataset fingerprints

`data/benchmarks/experimental_2_9/design_fingerprint.json` and split `fingerprint_manifest.json`. Bridge block: `data/benchmarks/experimental_2_13_bridges/`.
